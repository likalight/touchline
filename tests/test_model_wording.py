"""Explanations must name the input actually present and describe model estimates."""
from types import SimpleNamespace

import pytest

from touchline.agents.analyst import TacticalAnalyst, F
from touchline.agents.narrator import _render_frame
from touchline.i18n import BANKS


def test_absent_pressure_is_not_described_as_pressure_helping():
    analyst = TacticalAnalyst(None, None)
    features = {**analyst.m.shot_baseline, "bias": 1, "under_pressure": 0}
    enriched = SimpleNamespace(ev=SimpleNamespace(id="SHOT"), xg=analyst.m.xg.predict(features), xg_features=features)
    frames, _ = analyst.shot_reasons(enriched)
    factor = next(frame for frame in frames if frame["k"] == "r.top_factor")
    english = _render_frame(factor, "en", "analyst")
    assert "absence of defender pressure" in english
    assert "raised the model estimate versus baseline" in english
    assert "helped" not in english
    for lang in BANKS:
        rendered = _render_frame(factor, lang, "analyst")
        assert "@v." not in rendered and "no_under_pressure" not in rendered


@pytest.mark.parametrize("lang", BANKS)
def test_counterfactual_is_explicitly_a_model_estimate(lang):
    frame = F("r.counterfactual", ["SHOT"], change="@v.cf.five metres closer", xg_after=.28, xg_after_pct=28, delta=.17)
    stems = {"en":"Model estimate", "es":"Estimación del modelo", "fr":"Estimation du modèle", "pt":"Estimativa do modelo"}
    for persona in ("analyst", "casual"):
        rendered = _render_frame(frame, lang, persona)
        assert rendered.startswith(stems[lang])
        assert "@v." not in rendered and "{" not in rendered
