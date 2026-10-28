"""A rejected model answer must not be advertised as the answer's execution path."""
import asyncio
from copy import deepcopy

import pytest

from touchline.agents.ask import AskTheAnalyst
from touchline.judge import JudgeSession


QUESTION = "Explain how Varga recovered from his possession loss, using the linked match events."


@pytest.fixture(scope="module")
def replay():
    async def run():
        session = JudgeSession()
        session.paused = False
        async def fast_wait(seconds):
            await asyncio.sleep(0)
        session._wait = fast_wait
        await session._run()
        return session
    return asyncio.run(run())


class RejectedHostedAnswer:
    available = True
    backend = "foundry"
    evidence = {"request_id": "filmed-reproduction", "path": "foundry_hosted", "completed": True,
                "fallback": False, "model": "gpt-4.1-mini"}

    async def run(self, *args, **kwargs):
        return "Varga recovered because he refused to give up."  # not a source-selected statement

    def execution(self):
        return self.evidence


def test_actual_filmed_question_returns_verified_loss_and_recovery_with_honest_execution(replay):
    analyst = AskTheAnalyst(replay.state, lambda: replay.insights)
    model = RejectedHostedAnswer()
    analyst.llm = model
    answer = asyncio.run(analyst.ask(QUESTION))
    assert answer["source"] == "router" and answer["answer_type"] == "verified_player_story"
    assert "Redemption for Kofi Varga" in answer["answer"]
    assert "Kofi Varga lost possession" in answer["answer"]
    assert "rating" not in answer["answer"] and "refused to give up" not in answer["answer"]
    redemption = next(fr for ins in replay.insights for fr in ins["reasons"] if fr["k"] == "s.redemption")
    assert set(redemption["ev"]) <= set(answer["citations"])
    assert all(eid in replay.state.events for eid in answer["citations"])
    assert answer["fallback_reason"] == "unbound_model_answer"
    assert answer["execution"]["path"] == "application_fallback"
    assert answer["execution"]["fallback"] and answer["execution"]["completed"]
    assert answer["execution"]["model_attempted"]
    assert answer["execution"]["model_attempt"] == model.evidence
    assert model.evidence["path"] == "foundry_hosted" and not model.evidence["fallback"]
    assert answer["grounding"]["tool_results_accepted"] == 0


@pytest.mark.parametrize("case", ["none", "only_loss", "blocked", "other_player"])
def test_missing_supported_recovery_does_not_accept_the_question_premise(replay, case):
    insights = deepcopy(replay.insights)
    if case == "none":
        insights = []
    elif case == "only_loss":
        insights = [i for i in insights if not any(f["k"] == "s.redemption" for f in i["reasons"])]
    elif case == "blocked":
        for ins in insights:
            ins["verification"]["status"] = "blocked"
    else:
        for ins in insights:
            for fr in ins["reasons"]:
                if fr["k"] == "s.redemption":
                    fr["p"]["player"] = "Other Player"
    analyst = AskTheAnalyst(replay.state, lambda: insights)
    answer = analyst.route(QUESTION)
    assert answer["answer_type"] == "story_unavailable"
    assert "don't have a verified recovery storyline for Kofi Varga" in answer["answer"]
    assert answer["citations"] == []
    assert "rating" not in answer["answer"]


def test_offline_request_does_not_inherit_a_stale_model_attempt(replay):
    analyst = AskTheAnalyst(replay.state, lambda: replay.insights)
    model = RejectedHostedAnswer()
    model.available = False
    analyst.llm = model
    answer = asyncio.run(analyst.ask(QUESTION))
    assert answer["execution"]["model_attempt"] is None
    assert not answer["execution"]["model_attempted"]
    assert answer["fallback_reason"] == "model_unavailable"
    assert analyst.route("How is Varga playing?")["answer"].startswith("Kofi Varga (")


class SourceSelectingModel(RejectedHostedAnswer):
    def __init__(self, tool, arguments, indices):
        self.tool, self.arguments, self.indices = tool, arguments, indices

    async def run(self, *args, tools, **kwargs):
        import json
        result = json.loads(next(t for t in tools if t.__name__ == self.tool)(**self.arguments))
        return json.dumps({"answer_ids": [result["verified_answers"][i]["id"] for i in self.indices]})


@pytest.mark.parametrize("question,tool,arguments,indices", [
    ("Who won?", "get_scoreboard", {}, [0]),  # true minute, wrong subject
    ("Who won?", "get_scoreboard", {}, [1, 0]),  # a relevant fact cannot launder an irrelevant extra
    ("How many goals did Varga score?", "get_player_stats", {"name": "Mensah"}, [0]),
    (QUESTION, "get_player_stats", {"name": "Varga"}, [0]),  # stats do not substantiate recovery
    ("What is the xG?", "get_scoreboard", {}, [3]),  # possession is not xG
    ("Explain the latest goal", "list_key_moments", {"kind": "goal"}, [0]),  # genuine but older goal
])
def test_source_bound_but_irrelevant_selection_is_rejected(replay, question, tool, arguments, indices):
    analyst = AskTheAnalyst(replay.state, lambda: replay.insights)
    analyst.llm = SourceSelectingModel(tool, arguments, indices)
    answer = asyncio.run(analyst.ask(question))
    assert answer["source"] == "router"
    assert answer["fallback_reason"] == "source_selection_irrelevant"
    assert answer["execution"]["path"] == "application_fallback"


@pytest.mark.parametrize("question,tool,arguments,index,binding", [
    ("Who won?", "get_scoreboard", {}, 1, "score"),
    ("How many goals did Varga score?", "get_player_stats", {"name": "Varga"}, 0, "player_stats"),
    (QUESTION, "get_player_stats", {"name": "Varga"}, 1, "player_recovery"),
    ("What is the xG?", "get_scoreboard", {}, 2, "xg"),
    ("Explain the latest goal", "list_key_moments", {"kind": "goal"}, -1, "moment:goal"),
])
def test_relevant_typed_source_selections_still_pass(replay, monkeypatch, question, tool, arguments, index, binding):
    from touchline.safety import ContentSafety
    local = ContentSafety()
    local.endpoint = ""
    monkeypatch.setattr("touchline.safety.safety", local)
    analyst = AskTheAnalyst(replay.state, lambda: replay.insights)
    analyst.llm = SourceSelectingModel(tool, arguments, [index])
    answer = asyncio.run(analyst.ask(question))
    assert answer["source"] == "llm:foundry"
    assert answer["grounding"]["relevance_binding"] == binding
    if binding == "player_recovery":
        assert "Redemption for Kofi Varga" in answer["answer"] and answer["citations"]


def test_false_winner_premise_and_player_score_question_route_to_actual_facts(replay):
    analyst = AskTheAnalyst(replay.state, lambda: replay.insights)
    result = analyst.route("Why did Ironmoor win?")
    assert "Kestrel Bay FC lead Ironmoor Athletic 3-2" in result["answer"]  # Judge excerpt ends before full-time
    assert "goals: 3" in analyst.route("How many goals did Varga score?")["answer"]
    assert analyst.route("Compare Varga and Mensah")["answer_type"] == "comparison_unavailable"


def test_model_can_select_explicit_missing_recovery_without_inventing_it(replay, monkeypatch):
    from touchline.safety import ContentSafety
    local = ContentSafety()
    local.endpoint = ""
    monkeypatch.setattr("touchline.safety.safety", local)
    analyst = AskTheAnalyst(replay.state, lambda: [])
    analyst.llm = SourceSelectingModel("get_player_stats", {"name": "Varga"}, [1])
    answer = asyncio.run(analyst.ask(QUESTION))
    assert answer["source"] == "llm:foundry"
    assert "don't have a verified recovery storyline" in answer["answer"]
    assert not answer["citations"]
