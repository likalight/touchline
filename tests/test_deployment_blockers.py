"""Regression cases for cloud publication, session isolation and shared-feed delivery."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from touchline import llm as llm_module
from touchline.agents.ask import AskTheAnalyst


def test_tool_agents_and_verification_are_request_scoped(monkeypatch):
    import agent_framework
    from touchline import foundry_agents

    class FakeAgent:
        def __init__(self, client, instructions, name, tools=None, **kwargs):
            self.tools = tools

        async def run(self, prompt):
            result = json.loads(self.tools[0]())
            await asyncio.sleep(0)  # overlap tool execution and verification in other requests
            number = 999 if "invent" in prompt else result["minute"]
            return SimpleNamespace(text=f"Minute {number}.")

    monkeypatch.setattr(agent_framework, "Agent", FakeAgent)
    monkeypatch.setattr(foundry_agents, "hosted_agent", lambda *args: None)
    llm = llm_module.LLM()
    llm.client, llm.backend = object(), "foundry"
    monkeypatch.setattr("touchline.agents.ask.get_llm", lambda: llm)

    def make(minute):
        state = SimpleNamespace(snapshot=lambda: {"minute": minute, "score": {}, "home": {}, "away": {},
                                                  "win_prob": {}, "momentum": {}, "phase": {}})
        analyst = AskTheAnalyst(state, lambda: [])
        analyst.route = lambda q: {"answer": "fallback", "source": "router"}
        return analyst

    async def run():
        first, second = make(11), make(88)
        assert (await first.ask("minute?"))["answer"] == "Minute 11."
        assert (await second.ask("minute?"))["answer"] == "Minute 88."
        results = await asyncio.gather(first.ask("minute?"), second.ask("minute?"),
                                       first.ask("invent 999"), first.ask("minute?"))
        assert [r["answer"] for r in results] == ["Minute 11.", "Minute 88.", "fallback", "Minute 11."]
        restarted = make(3)
        assert (await restarted.ask("minute?"))["answer"] == "Minute 3."
        assert "AskTheAnalyst" not in llm._agents

    asyncio.run(run())


def test_hosted_fallback_keeps_current_request_tools(monkeypatch):
    import agent_framework
    from touchline import foundry_agents

    class FailingHosted:
        async def run(self, prompt):
            raise RuntimeError("hosted unavailable")

    class Local:
        def __init__(self, client, instructions, name, tools=None, **kwargs):
            self.tools = tools

        async def run(self, prompt):
            await asyncio.sleep(0)
            return SimpleNamespace(text=self.tools[0]())

    monkeypatch.setattr(foundry_agents, "hosted_agent", lambda *args: FailingHosted())
    monkeypatch.setattr(agent_framework, "Agent", Local)
    llm = llm_module.LLM()
    llm.client, llm.backend = object(), "foundry"

    async def run():
        return await asyncio.gather(llm.run("AskTheAnalyst", "", "", tools=[lambda: "first"]),
                                    llm.run("AskTheAnalyst", "", "", tools=[lambda: "second"]))

    assert asyncio.run(run()) == ["first", "second"]
    assert llm.fallbacks == 2 and llm.status()["hosted_agents"] == []


def test_publish_failure_is_not_success(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "foundry_publish.py"
    spec = importlib.util.spec_from_file_location("publish_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_MODEL", raising=False)
    assert module.main() == 1
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/project")
    monkeypatch.setenv("FOUNDRY_MODEL", "model")
    def unexpected_publication(*args):
        raise AssertionError("An invalid policy must be rejected before calling Foundry")
    monkeypatch.setattr(module, "publish", unexpected_publication)
    monkeypatch.delenv("FOUNDRY_RAI_POLICY", raising=False)
    assert module.main() == 1
    monkeypatch.setenv("FOUNDRY_RAI_POLICY", "Microsoft.DefaultV2")
    assert module.main() == 1
    monkeypatch.setenv("FOUNDRY_RAI_POLICY", "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/ai/raiPolicies/Microsoft.DefaultV2")
    monkeypatch.setattr(module, "publish", lambda *args: [{"name": "analyst", "version": None}])
    assert module.main() == 1
    monkeypatch.setattr(module, "publish", lambda *args: [{"name": "analyst", "version": "1"}, {"name": "narrator", "version": "2"}])
    assert module.main() == 0


def test_shared_live_controls_and_read_only_deployment(monkeypatch):
    from touchline import server
    monkeypatch.setenv("TOUCHLINE_AUTH", "entra")
    with TestClient(server.app) as client:
        server.sessions["live"] = server.sessions["demo"]
        assert client.post("/api/matches/live/control", json={"action": "pause"}).status_code == 401
        monkeypatch.setenv("TOUCHLINE_AUTH", "open")
        monkeypatch.setenv("TOUCHLINE_PROTECT_SHARED", "on")
        for sid in ("demo", "live"):
            assert client.get(f"/api/matches/{sid}").status_code == 200
            assert client.post(f"/api/matches/{sid}/control", json={"action": "pause"}).status_code == 403


@pytest.mark.parametrize("interrupted", [False, True])
def test_eventhub_consumer_does_not_steal_events(monkeypatch, interrupted):
    from touchline import server, feeds
    from touchline.sim.engine import simulate
    from touchline.runtime import MatchSession

    first_meta, first_events = simulate(3)
    if interrupted:
        first_events = first_events[:200]  # a replacement feed arrives without a full-time marker
    second_meta, second_events = simulate(4)
    completed = []

    class RecordedSession(MatchSession):
        async def _run(self):
            self.broadcast_outputs = False
            await super()._run()
            completed.append(self)

    async def payloads(**_kwargs):
        for meta, events in ((first_meta, first_events), (second_meta, second_events)):
            yield {"meta": meta.model_dump()}
            for event in events:
                yield event.model_dump()  # fill the queue; there must still be exactly one reader

    monkeypatch.setattr(server, "MatchSession", RecordedSession)
    monkeypatch.setattr(feeds, "eventhub_payloads", payloads)
    monkeypatch.setattr(server, "sessions", {})
    asyncio.run(server.hub_consumer())
    assert len(completed) == 2
    for session, events in zip(completed, (first_events, second_events)):
        assert list(session.state.events) == [event.id for event in events]
        assert session.guard.stats["accepted"] == len(events)
    assert completed[-1].state.status == "full_time"


@pytest.mark.parametrize("failure", [None, "offline", "router", "fallback"])
def test_deployment_smoke_requires_hosted_execution(monkeypatch, failure):
    import io
    from scripts import smoke_deployment

    llm = {"backend": "foundry", "hosted_agents": ["AskTheAnalyst"], "hosted_fallbacks": 0, "model": "test"}
    before = {"llm": dict(llm)}
    if failure == "offline":
        before["llm"]["backend"] = "offline"
    answer = {"source": "router" if failure == "router" else "llm:foundry", "answer": "0-0",
              "execution": {"path": "foundry_hosted", "completed": True, "fallback": failure == "fallback"},
              "grounding": {"tool_results": 1}}
    after = {"llm": {**llm, "hosted_fallbacks": int(failure == "fallback")}}
    replies = iter([before, {"state": {"minute": 1}}, answer, after])
    monkeypatch.setattr(smoke_deployment, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(next(replies)).encode()))
    if failure:
        with pytest.raises(RuntimeError):
            smoke_deployment.check("https://example.test")
    else:
        assert smoke_deployment.check("https://example.test")["passed"]
