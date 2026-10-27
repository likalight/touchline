"""Touchline's agents in Microsoft Foundry Agent Service.

The same agent definitions run three ways:

1. **Hosted in Foundry** (production): `scripts/foundry_publish.py` (run automatically by `azd up`)
   publishes each agent as a versioned prompt agent in the Foundry project, with a Responsible-AI
   content policy attached. At runtime `FoundryAgent` binds the published version to local tool
   implementations, so the instructions, model and safety policy are managed in Foundry while the
   tools stay next to the live match data. Set TOUCHLINE_FOUNDRY_AGENTS=on.
2. **Local Agent Framework agent** on any chat client (Foundry, Azure OpenAI, OpenAI-compatible).
3. **Offline**: deterministic routers and phrase banks; no model needed.

Every answer, on every path, goes through the FactChecker before anyone sees it.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

log = logging.getLogger("touchline.foundry")

# runtime agent name -> published Foundry agent
PUBLISHED = {"AskTheAnalyst": "touchline-analyst", "Narrator": "touchline-narrator"}


def definitions() -> dict[str, dict]:
    """Agent name -> description, instructions and (for tool-using agents) the tool functions."""
    from touchline.agents.ask import INSTRUCTIONS as ASK
    from touchline.agents.narrator import NARRATOR_INSTRUCTIONS as NARR

    return {
        "touchline-analyst": {
            "description": "Answers fan and producer questions about a live synthetic match, grounded in match-data tools, with event citations.",
            "instructions": ASK, "tools": "analyst"},
        "touchline-narrator": {
            "description": "Writes verified on-air graphics copy (title and lines) for one match moment, in any language, from structured facts.",
            "instructions": NARR, "tools": None},
    }


def tool_stubs() -> list[Callable]:
    """The analyst's tools, bound to an empty match, used only to publish their schemas."""
    from touchline.agents.ask import AskTheAnalyst
    from touchline.runtime import MatchSession

    s = MatchSession(seed=1, speed=1)
    return AskTheAnalyst(s.state, lambda: []).tools()


def hosted_agent(runtime_name: str, tools: Optional[list[Callable]] = None):
    """A FoundryAgent bound to the published version of this agent, or None if not enabled."""
    if os.getenv("TOUCHLINE_FOUNDRY_AGENTS", "").lower() != "on" or runtime_name not in PUBLISHED:
        return None
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        return None
    try:
        from agent_framework.foundry import FoundryAgent
        from azure.identity import DefaultAzureCredential

        return FoundryAgent(project_endpoint=endpoint, agent_name=PUBLISHED[runtime_name],
                            agent_version=os.getenv(f"TOUCHLINE_AGENT_VERSION_{PUBLISHED[runtime_name].split('-')[-1].upper()}") or None,
                            credential=DefaultAzureCredential(), tools=tools or None)
    except Exception as exc:  # pragma: no cover - depends on Azure
        log.warning("Foundry hosted agent %s unavailable, using a local agent: %s", runtime_name, exc)
        return None


def publish(endpoint: str, model: str, rai_policy: str, git_sha: str = "") -> list[dict]:
    """Publish (a new version of) every Touchline agent to Foundry Agent Service."""
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient, to_prompt_agent
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import RaiConfig
    from azure.identity import DefaultAzureCredential

    cred = DefaultAzureCredential()
    client = FoundryChatClient(project_endpoint=endpoint, model=model, credential=cred)
    project = AIProjectClient(endpoint=endpoint, credential=cred)
    out = []
    for name, d in definitions().items():
        tools = tool_stubs() if d["tools"] == "analyst" else None
        agent = Agent(client, d["instructions"], name=name, description=d["description"], tools=tools)
        definition = to_prompt_agent(agent, rai_config=RaiConfig(rai_policy_name=rai_policy))
        v = project.agents.create_version(agent_name=name, definition=definition, description=d["description"],
                                          metadata={"app": "touchline", "git": git_sha[:12] or "local"})
        out.append({"name": name, "version": getattr(v, "version", None) or v.get("version"), "tools": len(tools or [])})
        log.info("published %s version %s", name, out[-1]["version"])
    return out
