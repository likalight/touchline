"""Touchline as an MCP server: any agent (GitHub Copilot, Claude, a broadcaster's own) can use a live match.

Streamable HTTP at /mcp. In VS Code, `.vscode/mcp.json` adds it to GitHub Copilot's agent mode, so a
producer or developer can ask Copilot "why did Ironmoor score?" or "draft a half-time tweet for the
home side" and Copilot calls Touchline's verified tools instead of guessing.

The tools are read-only views of the match, plus the analyst agent (questions pass Prompt Shields first).
Every number they return comes from the same match state the FactChecker verifies against.
"""
from __future__ import annotations

import json
from typing import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

INSTRUCTIONS = """Touchline explains a live (synthetic, fictional) football match. Use list_matches first, then the
other tools with a session id ('demo' is always running). Quote numbers exactly as the tools return them and
cite event IDs like E01837 when you explain why something happened."""


def build(sessions: Callable[[], dict]) -> FastMCP:
    mcp = FastMCP("touchline", instructions=INSTRUCTIONS, stateless_http=True, json_response=True,
                  streamable_http_path="/mcp",
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    def get(session: str):
        s = sessions().get(session)
        if s is None:
            raise ValueError(f"unknown session '{session}'; call list_matches")
        return s

    def tools(session: str) -> dict:
        return {f.__name__: f for f in get(session).ask_agent.tools()}

    @mcp.tool()
    def list_matches() -> str:
        """Live matches: session id, clubs, score and minute."""
        out = []
        for sid, s in sessions().items():
            out.append({"session": sid, "home": s.meta.home.name, "away": s.meta.away.name,
                        "score": dict(s.state.score), "minute": s.state.minute, "finished": s.done})
        return json.dumps(out)

    @mcp.tool()
    def get_scoreboard(session: str = "demo") -> str:
        """Score, minute, possession, xG, shots, win probability, momentum and whether the game is in control or chaos."""
        return tools(session)["get_scoreboard"]()

    @mcp.tool()
    def get_key_moments(session: str = "demo", kind: str = "", lang: str = "en", limit: int = 8) -> str:
        """The latest verified moments with why they mattered, newest last. kind filters (goal, momentum, phase, press, story_duel...)."""
        s = get(session)
        out = []
        for i in [x for x in s.insights if not kind or x["kind"] == kind][-max(1, min(limit, 30)):]:
            from touchline.i18n import BANKS
            actual_lang = lang if lang in BANKS else "en"
            r = s.narrator.render(i, "analyst", actual_lang)
            out.append({"minute": i["minute"], "kind": i["kind"], "title": r.get("title"),
                        "why": [l["text"] for l in r.get("lines", [])], "evidence": i["event_ids"],
                        "language": actual_lang, "source": "checked_phrase_bank",
                        "verified": (i.get("verification") or {}).get("status") == "verified"})
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def explain_event(event_id: str, session: str = "demo") -> str:
        """Every derived fact for one event: xG, pass difficulty, threat added, win-probability change."""
        return tools(session)["explain_event"](event_id)

    @mcp.tool()
    def get_player(name: str, session: str = "demo") -> str:
        """One player's match: passes and accuracy, pass difficulty, xG, threat added, top speed, distance, rating."""
        return tools(session)["get_player_stats"](name)

    @mcp.tool()
    def get_team_report(side: str = "home", session: str = "demo") -> str:
        """Tactical picture for 'home' or 'away': pressing (PPDA), high turnovers, xG, shots, possession."""
        return tools(session)["get_team_report"](side)

    @mcp.tool()
    def get_recap(session: str = "demo", persona: str = "casual", lang: str = "en") -> str:
        """The match story so far (half-time or full-time recap) for a casual fan or an analyst, in a language."""
        return json.dumps(get(session).get_recap(persona if persona in ("casual", "analyst") else "casual", lang), ensure_ascii=False)

    @mcp.tool()
    def what_if(scenario: str = "", session: str = "demo") -> str:
        """Counterfactual: replay the rest of the match 1,000 times with one thing changed (a goal ruled out, a red card
        not given, an extra goal). Call with no scenario to list the options for this match."""
        from touchline.whatif import run, scenarios

        s = get(session)
        if not scenario:
            return json.dumps([{"id": x["id"], "label": x["label"]} for x in scenarios(s)])
        out = run(s, scenario)
        return json.dumps(out if out else {"error": "unknown scenario; call what_if with no scenario to list them"})

    @mcp.tool()
    async def ask_analyst(question: str, session: str = "demo", lang: str = "en") -> str:
        """Ask Touchline's analyst agent anything about the match; the answer cites event IDs."""
        from touchline.safety import safety

        if await safety.screen_question(question):
            return json.dumps({"answer": "I can only help with questions about this match.", "refused": True})
        res = await get(session).ask_agent.ask(question, lang)
        return json.dumps({k: res[k] for k in ("answer", "citations", "source") if k in res}, ensure_ascii=False)

    return mcp
