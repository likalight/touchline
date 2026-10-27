"""Foundry wiring that can be checked without Azure: agent definitions, published tool schemas, eval checks."""
import importlib.util
from pathlib import Path

from touchline.foundry_agents import definitions, hosted_agent, tool_stubs, strict_tool_schemas

spec = importlib.util.spec_from_file_location("feval", Path(__file__).resolve().parents[1] / "scripts" / "foundry_eval.py")
feval = importlib.util.module_from_spec(spec); spec.loader.exec_module(feval)


class Msg:
    def __init__(self, *texts):
        self.role = "tool"
        self.contents = [type("C", (), {"result": t, "text": None})() for t in texts]


def test_definitions_and_tool_schemas():
    d = definitions()
    assert set(d) == {"touchline-analyst", "touchline-narrator"}
    names = [f.__name__ for f in tool_stubs()]
    assert {"get_scoreboard", "get_events", "get_team_report", "explain_event"} <= set(names)
    assert all(f.__doc__ for f in tool_stubs())


def test_hosted_agent_off_without_env(monkeypatch):
    monkeypatch.delenv("TOUCHLINE_FOUNDRY_AGENTS", raising=False)
    assert hosted_agent("AskTheAnalyst") is None


def test_hosted_agent_uses_pinned_or_latest_published_version(monkeypatch):
    from unittest.mock import MagicMock
    import agent_framework.foundry
    import azure.ai.projects
    monkeypatch.setenv("TOUCHLINE_FOUNDRY_AGENTS", "on")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/p")
    monkeypatch.delenv("TOUCHLINE_AGENT_VERSION_ANALYST", raising=False)
    client = MagicMock()
    client.return_value.__enter__.return_value.agents.get.return_value.versions.latest.version = "7"
    factory = MagicMock()
    monkeypatch.setattr(azure.ai.projects, "AIProjectClient", client)
    monkeypatch.setattr(agent_framework.foundry, "FoundryAgent", factory)
    hosted_agent("AskTheAnalyst")
    assert factory.call_args.kwargs["agent_version"] == "7"
    client.reset_mock()
    monkeypatch.setenv("TOUCHLINE_AGENT_VERSION_ANALYST", "2")
    hosted_agent("AskTheAnalyst")
    assert factory.call_args.kwargs["agent_version"] == "2"
    client.assert_not_called()


def test_prompt_agent_definition_carries_tools_and_safety_policy():
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, to_prompt_agent
    from azure.ai.projects.models import RaiConfig
    from azure.core.credentials import AccessToken

    class Fake:
        def get_token(self, *a, **k):
            return AccessToken("x", 9999999999)

    c = FoundryChatClient(project_endpoint="https://example.services.ai.azure.com/api/projects/p", model="gpt-4.1-mini", credential=Fake())
    a = Agent(c, definitions()["touchline-analyst"]["instructions"], name="touchline-analyst", tools=tool_stubs())
    policy = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/ai/raiPolicies/Microsoft.DefaultV2"
    j = strict_tool_schemas(to_prompt_agent(a, rai_config=RaiConfig(rai_policy_name=policy))).as_dict()
    assert j["model"] == "gpt-4.1-mini" and len(j["tools"]) == 7 and j["rai_config"]["rai_policy_name"] == policy
    assert "get_source_scope" in {t["name"] for t in j["tools"]}
    for tool in j["tools"]:
        params = tool["parameters"]
        assert tool["strict"] and params["additionalProperties"] is False
        assert set(params["required"]) == set(params["properties"])
    events = next(t for t in j["tools"] if t["name"] == "get_events")
    assert events["parameters"]["properties"]["minute_from"]["type"] == "integer"


def test_touchline_eval_checks():
    conv = [Msg('{"score": {"home": 3, "away": 2}, "xg": 1.47}')]
    assert feval.grounded_numbers("score?", "Kestrel lead 3-2 on 1.47 xG.", conv)["passed"]
    assert not feval.grounded_numbers("score?", "Kestrel lead 4-2.", conv)["passed"]
    assert feval.cites_events("Why did they score?", "A late winner [E01837].", [Msg("E01837")])["passed"]
    assert not feval.cites_events("Why did they score?", "A late winner.")["passed"]
    assert feval.concise("One. Two. Three.") and not feval.concise("One. Two. Three. Four.")
