import math

import pytest

from touchline.agents.ingest import IngestGuard
from touchline.agents.verifier import FactChecker
from touchline.analytics.state import MatchState
from touchline.schema import Event
from touchline.sim.engine import simulate


@pytest.fixture(scope="module")
def match():
    meta, events = simulate(87)
    state = MatchState(meta)
    for event in events:
        state.apply(event)
    return state, events


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "NaN"])
@pytest.mark.parametrize("location", ["t", "x", "frame", "qualifiers"])
def test_ingest_quarantines_nonfinite_payloads_without_advancing_watermark(match, value, location):
    payload = match[1][0].model_dump()
    payload[location] = {"h9": [value, 12.0]} if location == "frame" else (
        {"nested": [{"measurement": value}]} if location == "qualifiers" else value)
    guard = IngestGuard()
    assert guard.push(payload) == []
    assert guard.stats["quarantined"] == 1 and guard.stats["accepted"] == 0
    assert not guard.seen and guard.next_seq == 1
    assert guard.push(match[1][0].model_dump()) == [match[1][0]]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "NaN"])
def test_nonfinite_claim_cannot_pass_tolerance_comparison(match, value):
    state, events = match
    shot = next(e for e in events if e.type == "shot")
    enriched = state.enriched[shot.id]
    claim = {"headline": {"k": "r.chance_quality", "ev": [shot.id],
                           "p": {"xg": value, "xg_pct": round(enriched.xg * 100)}},
             "reasons": [], "t": shot.t}
    checker = FactChecker(state)
    assert checker.check_insight(claim)["status"] == "blocked"
    claim["headline"]["p"]["xg"] = round(enriched.xg, 2)
    assert checker.check_insight(claim)["status"] == "verified"


def test_complete_synthetic_dataset_still_validates(match):
    for event in match[1]:
        validated = Event.model_validate(event.model_dump())
        assert math.isfinite(validated.t)


@pytest.mark.parametrize("value", ["1e1000", "fast", True, None])
def test_numeric_qualifiers_cannot_crash_analytics_with_other_types(match, value):
    payload = match[1][0].model_dump()
    payload["qualifiers"] = {"distance_m": value}
    guard = IngestGuard()
    assert guard.push(payload) == [] and guard.stats["quarantined"] == 1
