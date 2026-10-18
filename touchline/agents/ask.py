"""AskTheAnalyst - natural-language Q&A over the live match ("why did they score?").

With an LLM backend this is an Agent Framework agent with function tools over the
match state; every number in its answer must appear in a tool result or the answer is
replaced by the deterministic router's. Offline, a keyword router answers directly.
Also exposed to other agents over A2A (see touchline/a2a.py).
"""
from __future__ import annotations

import json
import re
from difflib import get_close_matches
from typing import Callable, Optional

from touchline.agents.verifier import NUM_RE
from touchline.analytics.state import MatchState
from touchline.llm import get_llm

INSTRUCTIONS = """You are Touchline's match analyst. Answer questions about the live (synthetic) match
using ONLY the provided tools; never invent numbers or players. Be concise (max 3 sentences), explain
*why* not just *what*, and cite event IDs in square brackets when a tool returns them, e.g. [E00412].
Answer in the user's language."""


class AskTheAnalyst:
    name = "AskTheAnalyst"
    role = "Answers fan and producer questions with tool-grounded, cited answers"

    def __init__(self, state: MatchState, insights: Callable[[], list[dict]]):
        self.s = state
        self.insights = insights
        self.llm = get_llm()
        self._tool_log: list[str] = []

    # ------------------------------------------------------------------ tools
    def tools(self) -> list[Callable]:
        s = self.s
        log = self._tool_log

        def get_scoreboard() -> str:
            """Current score, minute, possession, xG, shots, win probability, momentum and control-vs-chaos phase."""
            snap = s.snapshot()
            out = json.dumps({k: snap[k] for k in ("minute", "score", "home", "away", "win_prob", "momentum", "phase")})
            log.append(out)
            return out

        def get_player_stats(name: str) -> str:
            """Stats for one player by (partial) name: passes, pass difficulty, xG, xT, speed, distance, rating."""
            pid = self._find_player(name)
            out = json.dumps({**s.player_summary(pid), "rating": s.player_rating(pid)}) if pid else '{"error": "unknown player"}'
            log.append(out)
            return out

        def list_key_moments(kind: str = "") -> str:
            """Most recent verified insights (optionally filtered by kind, e.g. goal, momentum, phase, press)."""
            ins = [i for i in self.insights() if not kind or i["kind"] == kind][-6:]
            out = json.dumps([{"minute": i["minute"], "kind": i["kind"], "event_ids": i["event_ids"],
                               "summary": i["renders"]["analyst"]["en"]["title"] if "renders" in i else i["kind"],
                               "why": [l["text"] for l in i.get("renders", {}).get("analyst", {}).get("en", {}).get("lines", [])]}
                              for i in ins])
            log.append(out)
            return out

        def explain_event(event_id: str) -> str:
            """All derived facts for one event ID (xG, pass difficulty, threat added, win-probability change)."""
            en = s.enriched.get(event_id)
            out = json.dumps(en.facts()) if en else '{"error": "unknown event"}'
            log.append(out)
            return out

        def get_events(minute_from: int, minute_to: int, event_type: str = "") -> str:
            """Raw match events between two minutes (inclusive), optionally one type (pass, shot, tackle, goal, card...).
            Returns at most 15, newest first, each with its event ID for citation."""
            out_l = []
            for e in reversed(list(s.events.values())):
                if minute_from <= e.minute <= minute_to and (not event_type or e.type == event_type):
                    out_l.append({"id": e.id, "minute": e.minute, "type": e.type, "team": e.team, "outcome": e.outcome,
                                  "player": s.players[e.player_id].name if e.player_id in s.players else None})
                    if len(out_l) >= 15:
                        break
            out = json.dumps(out_l)
            log.append(out)
            return out

        def get_team_report(side: str) -> str:
            """Tactical picture for one team ('home' or 'away'): pressing (PPDA, pressures, high turnovers), xG, shots, possession."""
            side = side if side in ("home", "away") else "home"
            t = s.team[side]
            out = json.dumps({"team": s.meta.home.name if side == "home" else s.meta.away.name, "ppda": s.ppda(side),
                              "pressures": int(t["pressures"]), "high_turnovers": int(t["high_turnovers"]),
                              "xg": round(t["xg"], 2), "shots": int(t["shots"]), "possession_pct": s.possession_pct()[side],
                              "phase": s.phase()})
            log.append(out)
            return out

        return [get_scoreboard, get_player_stats, list_key_moments, explain_event, get_events, get_team_report]

    def _find_player(self, name: str) -> Optional[str]:
        names = {p.name.lower(): pid for pid, p in self.s.players.items()}
        last = {p.name.split()[-1].lower(): pid for pid, p in self.s.players.items()}
        n = name.lower().strip()
        if n in names:
            return names[n]
        if n in last:
            return last[n]
        m = get_close_matches(n, list(names) + list(last), n=1, cutoff=0.75)
        if m:
            return names.get(m[0]) or last.get(m[0])
        return None

    # ------------------------------------------------------------------ answer
    async def ask(self, question: str, lang: str = "en") -> dict:
        if self.llm.available:
            self._tool_log.clear()
            text = await self.llm.run("AskTheAnalyst", INSTRUCTIONS, f"[lang={lang}] {question}", timeout=12.0, tools=self.tools())
            if text:
                corpus = " ".join(self._tool_log)
                bad = [n for n in NUM_RE.findall(text) if n not in corpus and n not in question]
                if not bad:
                    return {"answer": text, "citations": re.findall(r"E\d{5}", text), "source": f"llm:{self.llm.backend}"}
        return self.route(question)

    def route(self, q: str) -> dict:
        s = self.s
        ql = q.lower()
        h, a = s.meta.home, s.meta.away
        tn = {"home": h.name, "away": a.name}
        # player mentioned?
        for p in s.players.values():
            if p.name.lower() in ql or re.search(rf"\b{re.escape(p.name.split()[-1].lower())}\b", ql):
                ps = s.player_summary(p.id)
                return {"answer": (f"{ps['name']} ({tn[p.team]}, #{ps['number']} {ps['position']}): rating {s.player_rating(p.id)}, "
                                   f"{ps['passes']} passes at {ps['pass_accuracy']}% (avg difficulty {ps['avg_pass_difficulty']}/100), "
                                   f"{ps['xg']} xG, goals: {ps['goals']}, {ps['xt_added']} xT added, top speed {ps['top_speed_kmh']} km/h, "
                                   f"{ps['distance_km']} km covered."), "citations": [], "source": "router"}
        if re.search(r"\bwhy\b", ql):
            kinds = ["goal", "momentum", "phase", "press", "chance_saved", "chance_missed", "line_break", "wp_swing"]
            syn = {"score": "goal", "scored": "goal", "goal": "goal", "momentum": "momentum", "control": "phase",
                   "chaos": "phase", "press": "press", "save": "chance_saved", "miss": "chance_missed"}
            want = next((v for k, v in syn.items() if k in ql), None)
            ins = [i for i in self.insights() if (want is None or i["kind"] == want) and "renders" in i]
            if ins:
                i = ins[-1]
                r = i["renders"]["analyst"]["en"]
                return {"answer": f"{r['title']} ({i['minute']}'): " + "; ".join(l["text"] for l in r["lines"]),
                        "citations": i["event_ids"], "source": "router"}
        if any(w in ql for w in ("best", "standout", "player of", "motm", "man of the match")):
            top = s.top_players(3)
            return {"answer": "Top performers so far: " + "; ".join(
                f"{p['name']} ({tn[p['team']]}) {p['rating']}" for p in top) + ".", "citations": [], "source": "router"}
        if "xg" in ql or "expected" in ql or "chances" in ql:
            return {"answer": f"xG: {h.name} {round(s.team['home']['xg'], 2)} - {round(s.team['away']['xg'], 2)} {a.name} "
                              f"from {int(s.team['home']['shots'])} and {int(s.team['away']['shots'])} shots.",
                    "citations": [], "source": "router"}
        if "possession" in ql or "ball" in ql:
            pp = s.possession_pct()
            return {"answer": f"Possession: {h.name} {pp['home']}% - {pp['away']}% {a.name}.", "citations": [], "source": "router"}
        if any(w in ql for w in ("win", "probab", "odds", "chance of")):
            wp = s.wp
            return {"answer": f"Win probability: {h.name} {round(wp['home'] * 100)}%, draw {round(wp['draw'] * 100)}%, "
                              f"{a.name} {round(wp['away'] * 100)}%.", "citations": [], "source": "router"}
        if "press" in ql:
            return {"answer": f"Pressing: {h.name} {int(s.team['home']['pressures'])} pressures (PPDA {s.ppda('home')}), "
                              f"{a.name} {int(s.team['away']['pressures'])} (PPDA {s.ppda('away')}).", "citations": [], "source": "router"}
        if any(w in ql for w in ("fast", "speed", "quick")):
            r = s.records
            lab = {"longest_pass_m": ("Longest pass", "m"), "fastest_pass_kmh": ("Fastest pass", "km/h"),
                   "top_speed_kmh": ("Top speed", "km/h"), "fastest_shot_kmh": ("Fastest shot", "km/h")}
            parts = [f"{lab[k][0]} {v['value']} {lab[k][1]} by {v['player']} ({v['minute']}')" for k, v in r.items() if k in lab]
            return {"answer": "Match records - " + "; ".join(parts), "citations": [v["event_id"] for v in r.values()],
                    "source": "router"}
        ph = s.phase()
        return {"answer": f"{s.minute}': {h.name} {s.score['home']}-{s.score['away']} {a.name}. The game is "
                          f"{ph['label'].replace('_', ' ')} right now ({ph['turnovers_per_min']} turnovers/min). "
                          f"Ask me about a player, xG, momentum, pressing or why a goal happened.",
                "citations": [], "source": "router"}
