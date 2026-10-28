"""Question-specific evaluation regressions; no hosted model or evaluator calls."""
import copy
import json

import pytest

from scripts.foundry_eval import bounded_checks, source_oracle, rescore_bounded
from scripts.evidence_provenance import ROOT, fingerprint
from touchline.sim.engine import MatchSimulator


@pytest.fixture(scope="module")
def oracle():
    sim = MatchSimulator(87, match_id="SYN-00087")
    return source_oracle(sim.meta, list(sim.run()))


def last_goal_answer(oracle):
    g = oracle["last_goal"]
    return {"answer": f"{g['minute']}': GOAL! {g['scorer']} scores for {g['team']}. Chance quality: 0.11 xG.",
            "citations": [g["id"]]}


def test_last_goal_oracle_accepts_bound_identity_and_context(oracle):
    assert all(bounded_checks("event", last_goal_answer(oracle), oracle).values())


@pytest.mark.parametrize("mutation", ["earlier_goal", "wrong_scorer", "wrong_minute", "bare_citation", "no_explanation", "malformed_citations"])
def test_last_goal_oracle_rejects_irrelevance_and_identity_swaps(oracle, mutation):
    answer = last_goal_answer(oracle)
    if mutation == "earlier_goal":
        answer = {"answer": "28': GOAL! Theo Mensah scores for Ironmoor Athletic. Chance quality: 0.11 xG.",
                  "citations": ["E00562"]}
        assert "E00562" in oracle["event_ids"]  # valid citation alone must not pass
    elif mutation == "wrong_scorer":
        answer["answer"] = answer["answer"].replace(oracle["last_goal"]["scorer"], "Theo Mensah")
    elif mutation == "wrong_minute":
        answer["answer"] = answer["answer"].replace("90'", "44'")
    elif mutation == "bare_citation":
        answer["answer"] = "The game is interesting."
    elif mutation == "no_explanation":
        answer["answer"] = answer["answer"].split(". Chance")[0]
    else:
        answer["citations"] = oracle["last_goal"]["id"]
    assert not all(bounded_checks("event", answer, oracle).values())


def test_score_oracle_rejects_reversed_winner_even_with_correct_score(oracle):
    text = f"{oracle['home']} 3-2 {oracle['away']}. {oracle['away']} beat {oracle['home']}."
    checks = bounded_checks("score", {"answer": text, "citations": []}, oracle)
    assert checks["ordered_score"] and not checks["no_reversed_winner"]


def test_player_oracle_rejects_other_players_goal_count(oracle):
    answer = {"answer": "Kofi Varga played well. Theo Mensah scored 3 goals.", "citations": []}
    assert not bounded_checks("player", answer, oracle)["player_goals"]


def test_rescore_keeps_execution_and_raw_answers_and_preserves_original(tmp_path, oracle):
    report = {"provenance": {"simulator_sha256": fingerprint(ROOT.glob("touchline/sim/*.py")),
                             "generated_at": "original observation"},
              "seed": 87, "summary": {"attempted": 1, "hosted": 1, "passed": 1}, "passed": True,
              "cases": [{"id": "event", "answer": last_goal_answer(oracle), "checks": {"cited_event": True},
                         "duration_ms": 123, "hosted_success": True, "passed": True}]}
    report["cases"][0]["answer"]["execution"] = {"request_id": "original-request"}
    source, output = tmp_path / "original.json", tmp_path / "new.json"
    source.write_text(json.dumps(report), encoding="utf-8")
    original = source.read_bytes()
    assert rescore_bounded(source, output) == 0
    rescored = json.loads(output.read_text(encoding="utf-8"))
    assert source.read_bytes() == original
    assert rescored["provenance"] == report["provenance"]
    assert rescored["cases"][0]["answer"] == report["cases"][0]["answer"]
    assert rescored["cases"][0]["duration_ms"] == 123
    assert rescored["rescore"]["model_calls"] == 0
    with pytest.raises(ValueError, match="different file"):
        rescore_bounded(source, source)
    changed = copy.deepcopy(report)
    changed["provenance"]["simulator_sha256"] = "different-source"
    source.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="Simulator fingerprint differs"):
        rescore_bounded(source, output)
