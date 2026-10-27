"""Foundry wiring that can be checked without Azure: agent definitions, published tool schemas, eval checks."""
import importlib.util
from pathlib import Path

from touchline.foundry_agents import definitions, hosted_agent, tool_stubs

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
    j = to_prompt_agent(a, rai_config=RaiConfig(rai_policy_name=policy)).as_dict()
    assert j["model"] == "gpt-4.1-mini" and len(j["tools"]) == 6 and j["rai_config"]["rai_policy_name"] == policy


def test_touchline_eval_checks():
    conv = [Msg('{"score": {"home": 3, "away": 2}, "xg": 1.47}')]
    assert feval.grounded_numbers("score?", "Kestrel lead 3-2 on 1.47 xG.", conv)["passed"]
    assert not feval.grounded_numbers("score?", "Kestrel lead 4-2.", conv)["passed"]
    assert feval.cites_events("Why did they score?", "A late winner [E01837].", [Msg("E01837")])["passed"]
    assert not feval.cites_events("Why did they score?", "A late winner.")["passed"]
    assert feval.concise("One. Two. Three.") and not feval.concise("One. Two. Three. Four.")
