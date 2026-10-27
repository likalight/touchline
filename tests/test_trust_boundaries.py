"""Adversarial contracts: correct tokens do not imply a correct football claim."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from touchline.agents.ask import AskTheAnalyst
from touchline.agents.ingest import IngestGuard
from touchline.agents.verifier import FactChecker
from touchline.analytics.state import MatchState
from touchline.safety import ContentSafety
from touchline.sim.engine import simulate


@pytest.fixture(scope="module")
def match():
    meta, events = simulate(87)
    state = MatchState(meta)
    for event in events:
        state.apply(event)
    return state, events


def goal_claim(state, events):
    goal = next(e for e in events if e.type == "goal")
    team = state.meta.home if goal.team == "home" else state.meta.away
    return {"headline": {"k": "h.goal", "ev": [goal.id],
                         "p": {"player": state.name(goal.player_id), "team": team.name}},
            "reasons": [], "t": goal.t}


@pytest.mark.parametrize("mutation", ["scorer", "team", "event_type", "unknown_frame", "no_evidence", "future"])
def test_goal_claim_binds_identity_and_event(match, mutation):
    state, events = match
    checker = FactChecker(state)
    claim = goal_claim(state, events)
    assert checker.check_insight(claim)["status"] == "verified"
    bad = deepcopy(claim)
    if mutation == "scorer":
        bad["headline"]["p"]["player"] = state.name("a9")
    elif mutation == "team":
        bad["headline"]["p"]["team"] = state.meta.away.name
    elif mutation == "event_type":
        bad["headline"]["ev"] = [events[0].id]
    elif mutation == "unknown_frame":
        bad["headline"]["k"] = "h.unverified_claim"
    elif mutation == "no_evidence":
        bad["headline"]["ev"] = []
    else:
        bad["t"] = 0
    assert checker.check_insight(bad)["status"] == "blocked"


def test_final_score_is_bound_to_team_and_count(match):
    state, events = match
    final = events[-1]
    claim = {"headline": {"k": "h.full_time", "ev": [final.id], "p": {
        "home": state.meta.home.name, "away": state.meta.away.name,
        "score_home": 3, "score_away": 2}}, "reasons": [], "t": final.t}
    checker = FactChecker(state)
    assert checker.check_insight(claim)["status"] == "verified"
    claim["headline"]["p"].update(score_home=2, score_away=3)
    assert checker.check_insight(claim)["status"] == "blocked"


class SelectingModel:
    available = True
    backend = "test"

    def __init__(self, mode):
        self.mode = mode

    async def run(self, *args, tools, **kwargs):
        scoreboard = json.loads(next(t for t in tools if t.__name__ == "get_scoreboard")())
        if self.mode == "wrong_winner":
            return "Ironmoor Athletic beat Kestrel Bay FC 3-2."
        if self.mode == "wrong_id":
            return json.dumps({"answer_ids": ["A99_0"]})
        if self.mode == "fabricated_cause":
            return "Kestrel Bay FC won because Ironmoor Athletic stopped trying."
        return json.dumps({"answer_ids": [scoreboard["verified_answers"][1]["id"]]})


@pytest.mark.parametrize("mode", ["wrong_winner", "wrong_id", "fabricated_cause"])
def test_unbound_model_answers_fall_back_to_true_score(match, monkeypatch, mode):
    monkeypatch.setattr("touchline.safety.safety", ContentSafety())
    state, _ = match
    analyst = AskTheAnalyst(state, lambda: [])
    analyst.llm = SelectingModel(mode)
    answer = asyncio.run(analyst.ask("Who won?"))
    assert answer["source"] == "router"
    assert answer["fallback_reason"] == "unbound_model_answer"
    assert "Kestrel Bay FC beat Ironmoor Athletic 3-2" in answer["answer"]


def test_model_can_select_a_source_bound_answer(match, monkeypatch):
    local = ContentSafety()
    local.endpoint = ""
    monkeypatch.setattr("touchline.safety.safety", local)
    state, _ = match
    analyst = AskTheAnalyst(state, lambda: [])
    analyst.llm = SelectingModel("correct")
    answer = asyncio.run(analyst.ask("Who won?", lang="fr"))
    assert answer["source"] == "llm:test"
    assert answer["grounding"]["claims_bound"]
    assert answer["language"] == "en"  # no false promise that selected English was translated
    assert "Kestrel Bay FC beat Ironmoor Athletic 3-2" in answer["answer"]


def test_late_event_is_quarantined_after_gap_timeout(match):
    _, events = match
    guard = IngestGuard()
    output = []
    with patch("touchline.agents.ingest.time.monotonic", return_value=0) as clock:
        for event in (events[0], events[2]):
            output.extend(guard.push(event.model_dump()))
        clock.return_value = 2
        output.extend(guard.release())
        output.extend(guard.push(events[1].model_dump()))
        output.extend(guard.flush())
    assert [e.seq for e in output] == [1, 3]
    assert guard.stats["accepted"] == 2
    assert guard.stats["late_events"] == guard.stats["quarantined"] == 1
    assert guard.quarantine[-1]["error"] == "late_after_watermark"


def test_reorder_within_window_preserves_all_events(match):
    _, events = match
    guard = IngestGuard()
    with patch("touchline.agents.ingest.time.monotonic", return_value=0):
        output = [e for index in (0, 2, 1) for e in guard.push(events[index].model_dump())]
    assert [e.seq for e in output] == [1, 2, 3]
    assert guard.stats["late_events"] == 0


def test_conflicting_pending_sequence_is_quarantined(match):
    _, events = match
    guard = IngestGuard()
    with patch("touchline.agents.ingest.time.monotonic", return_value=0):
        assert not guard.push(events[2].model_dump())
        conflict = {**events[2].model_dump(), "id": "conflicting-id"}
        assert not guard.push(conflict)
        output = guard.flush()
    assert [e.id for e in output] == [events[2].id]
    assert guard.quarantine[-1]["error"] == "conflicting_sequence"


def test_moderation_outage_is_not_cached_as_safe(monkeypatch):
    monkeypatch.delenv("TOUCHLINE_SAFETY", raising=False)
    service = ContentSafety()
    service.endpoint = "https://audit.invalid"
    replies = [None, {"categoriesAnalysis": [{"category": category, "severity": 0}
                      for category in ("Hate", "SelfHarm", "Sexual", "Violence")]}]

    async def post(*args):
        return replies.pop(0)
    service._post = post
    failed = asyncio.run(service.moderate("An ordinary football question"))
    assert not failed["ok"] and failed["status"] == "unavailable"
    assert not service.cache
    recovered = asyncio.run(service.moderate("An ordinary football question"))
    assert recovered["ok"] and recovered["status"] == "checked"
    assert not replies


def test_prompt_shield_outage_has_explicit_refusal(monkeypatch):
    monkeypatch.delenv("TOUCHLINE_SAFETY", raising=False)
    service = ContentSafety()
    service.endpoint = "https://audit.invalid"

    async def post(*args):
        return None
    service._post = post
    assert asyncio.run(service.screen_question("Who won?")) == "safety_unavailable"


def test_local_mode_is_not_reported_as_hosted_moderation():
    service = ContentSafety()
    service.endpoint = ""
    result = asyncio.run(service.moderate("Who won?"))
    assert result["source"] == "local" and result["status"] == "not_configured"


@pytest.mark.parametrize("response", [{}, {"categoriesAnalysis": []},
                                    {"categoriesAnalysis": [{"category": "Hate"}]}])
def test_incomplete_moderation_response_is_unavailable(monkeypatch, response):
    monkeypatch.delenv("TOUCHLINE_SAFETY", raising=False)
    service = ContentSafety()
    service.endpoint = "https://audit.invalid"

    async def post(*args):
        return response
    service._post = post
    result = asyncio.run(service.moderate("Who won?"))
    assert not result["ok"] and result["status"] == "unavailable"


def test_integer_trailing_zero_is_not_a_rounding_equivalent(match):
    state, events = match
    claim = goal_claim(state, events)
    claim.update(minute=11, score={"home": 1, "away": 0})
    checker = FactChecker(state)
    assert any("110" in issue for issue in checker.check_text(claim, ["110 minutes"]))


@pytest.mark.parametrize("source,altered", [
    ("Kestrel Bay FC won 2-1.", "Kestrel Bay FC won 2-2."),
    ("7 pressures, 3 turnovers in 5 minutes", "7 pressures, 3 turnovers in 7 minutes"),
    ("2 shots in 5 minutes", "5 shots in 2 minutes"),
    ("Kofi Varga scores for Kestrel Bay FC", "Theo Mensah scores for Kestrel Bay FC"),
    ("Kofi Varga passed to Theo Mensah", "Theo Mensah passed to Kofi Varga"),
    ("Kestrel Bay FC beat Ironmoor Athletic 3-2", "Ironmoor Athletic beat Kestrel Bay FC 3-2"),
])
def test_rewrite_preserves_per_line_quantity_and_entity_associations(match, source, altered):
    checker = FactChecker(match[0])
    assert checker.check_rewrite([source], [altered])
    assert not checker.check_rewrite([source], [source.upper()])


def test_rewrite_allows_decimal_formatting_but_not_dropped_source_line(match):
    checker = FactChecker(match[0])
    assert not checker.check_rewrite(["Kofi Varga: 1.0 xG"], ["Kofi Varga: 1 xG"])
    assert checker.check_rewrite(["Kofi Varga: 1.0 xG", "2 goals"], ["Kofi Varga: 1 xG"])


def test_record_scope_is_available_to_model_and_explicit_about_language(match, monkeypatch):
    from touchline.agents.ask import SOURCE_SCOPE
    from scripts.foundry_eval import explicit_record_scope

    class ScopeModel:
        available = True
        backend = "test"

        async def run(self, *args, tools, **kwargs):
            result = json.loads(next(t for t in tools if t.__name__ == "get_source_scope")())
            scope = result["verified_answers"][0]
            assert scope["language"] == "en" and scope["answer_type"] == "source_scope"
            return json.dumps({"answer_ids": [scope["id"]]})

    local = ContentSafety()
    local.endpoint = ""
    monkeypatch.setattr("touchline.safety.safety", local)
    analyst = AskTheAnalyst(match[0], lambda: [])
    analyst.llm = ScopeModel()
    answer = asyncio.run(analyst.ask("Did Kofi Varga set an all-time Premier League world record?", lang="es"))
    assert answer["source"] == "llm:test" and answer["answer"] == SOURCE_SCOPE
    assert answer["language"] == "en" and answer["citations"] == []
    assert explicit_record_scope(answer["answer"])


def test_irrelevant_source_bound_fact_cannot_answer_historical_record_question(match, monkeypatch):
    from touchline.agents.ask import SOURCE_SCOPE
    from scripts.foundry_eval import explicit_record_scope

    local = ContentSafety()
    local.endpoint = ""
    monkeypatch.setattr("touchline.safety.safety", local)
    analyst = AskTheAnalyst(match[0], lambda: [])
    analyst.llm = SelectingModel("correct")  # selects a genuine scoreboard, but irrelevant to a world record
    answer = asyncio.run(analyst.ask("Did Kofi Varga set a world record?"))
    assert answer["source"] == "router" and answer["fallback_reason"] == "source_scope_missing"
    assert answer["answer"] == SOURCE_SCOPE
    assert not explicit_record_scope("44': GOAL! Kofi Varga scores for Kestrel Bay FC.")
    assert not explicit_record_scope("This fictional player scored 2 goals.")
    assert explicit_record_scope(answer["answer"])
    # The within-match records feature remains available; it is a different scope.
    assert analyst.route("Who ran fastest in this match?")["answer"].startswith("Match records")
