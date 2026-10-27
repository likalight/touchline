"""AskTheAnalyst - natural-language Q&A over the live match ("why did they score?").

With an LLM backend this is an Agent Framework agent with function tools over the
match state. The model selects source-rendered statements from those tools; it cannot
publish arbitrary paraphrases. Offline, a keyword router answers directly.
Also exposed to other agents over A2A (see touchline/a2a.py).
"""
from __future__ import annotations

import json
import re
from difflib import get_close_matches
from typing import Callable, Optional

from touchline.analytics.state import MatchState
from touchline.llm import get_llm

INSTRUCTIONS = """You are Touchline's match analyst. Use the tools to investigate the live synthetic
match and select the most relevant source-rendered statements. Each tool returns verified_answers:
records with id, answer, citations and language. Return ONLY JSON {"answer_ids":["id"]}, selecting
at most three records actually returned in this request. Do not compose, translate or rewrite facts.
Use list_key_moments for why/context questions and get_scoreboard for the score or winner.
If the requested fact is unavailable, return {"answer_ids":[]}. Language availability is explicit
in each record; never label an English answer as another language."""


class AskTheAnalyst:
    name = "AskTheAnalyst"
    role = "Answers fan and producer questions with tool-grounded, cited answers"

    def __init__(self, state: MatchState, insights: Callable[[], list[dict]]):
        self.s = state
        self.insights = insights
        self.llm = get_llm()

    @staticmethod
    def _source_copy(ins: dict) -> dict:
        """Render checked frames directly; never promote a generated preview to source truth."""
        from touchline.agents.narrator import _render_frame, MAX_LINES
        return {"title": _render_frame(ins["headline"], "en", "analyst"),
                "lines": [{"text": _render_frame(fr, "en", "analyst")} for fr in ins["reasons"]
                          if "analyst" in fr["aud"]][:MAX_LINES["analyst"]]}

    # ------------------------------------------------------------------ tools
    def tools(self, tool_log: Optional[list[str]] = None) -> list[Callable]:
        s = self.s
        log = tool_log if tool_log is not None else []

        def record(data: dict, answers: list[dict]) -> str:
            """Assign IDs within this request only; source text stays bound to its citations."""
            data["verified_answers"] = [{"id": f"A{len(log)}_{i}", "answer": a["answer"],
                                          "citations": a.get("citations", []), "language": "en"}
                                         for i, a in enumerate(answers)]
            out = json.dumps(data)
            log.append(out)
            return out

        def get_scoreboard() -> str:
            """Current score, minute, possession, xG, shots, win probability, momentum and control-vs-chaos phase."""
            snap = s.snapshot()
            return record({k: snap[k] for k in ("minute", "score", "home", "away", "win_prob", "momentum", "phase")},
                          [{"answer": f"Minute {snap['minute']}."}] +
                          [self.route(q) for q in ("score", "xg", "possession", "win probability", "pressing")])

        def get_player_stats(name: str) -> str:
            """Stats for one player by (partial) name: passes, pass difficulty, xG, xT, speed, distance, rating."""
            pid = self._find_player(name)
            return record({**s.player_summary(pid), "rating": s.player_rating(pid)},
                          [self.route(s.players[pid].name)]) if pid else record({"error": "unknown player"}, [])

        def list_key_moments(kind: str = "") -> str:
            """Most recent verified insights (optionally filtered by kind, e.g. goal, momentum, phase, press)."""
            ins = [i for i in self.insights() if (not kind or i["kind"] == kind)
                   and i.get("verification", {}).get("status") == "verified"][-6:]
            moments = [{"minute": i["minute"], "kind": i["kind"], "event_ids": i["event_ids"],
                               "summary": self._source_copy(i)["title"],
                               "why": [l["text"] for l in self._source_copy(i)["lines"]]}
                       for i in ins]
            return record({"moments": moments}, [{"answer": f"{i['minute']}': {i['summary']} " + "; ".join(i["why"]),
                                                  "citations": i["event_ids"]} for i in moments])

        def explain_event(event_id: str) -> str:
            """All derived facts for one event ID (xG, pass difficulty, threat added, win-probability change)."""
            en = s.enriched.get(event_id)
            if not en:
                return record({"error": "unknown event"}, [])
            facts = en.facts()
            text = f"{en.ev.minute}': {en.player_name or en.ev.team or 'Match'} — {en.ev.type} ({en.ev.outcome or 'recorded'})."
            if en.xg is not None:
                text += f" Model chance estimate: {round(en.xg, 2)} xG."
            return record(facts, [{"answer": text, "citations": [en.ev.id]}])

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
            return record({"events": out_l}, [{"answer": f"{e['minute']}': {e['player'] or e['team'] or 'Match'} — "
                                               f"{e['type']} ({e['outcome'] or 'recorded'}).", "citations": [e["id"]]}
                                              for e in out_l])

        def get_team_report(side: str) -> str:
            """Tactical picture for one team ('home' or 'away'): pressing (PPDA, pressures, high turnovers), xG, shots, possession."""
            side = side if side in ("home", "away") else "home"
            t = s.team[side]
            report = {"team": s.meta.home.name if side == "home" else s.meta.away.name, "ppda": s.ppda(side),
                              "pressures": int(t["pressures"]), "high_turnovers": int(t["high_turnovers"]),
                              "xg": round(t["xg"], 2), "shots": int(t["shots"]), "possession_pct": s.possession_pct()[side],
                              "phase": s.phase()}
            return record(report, [{"answer": f"{report['team']}: {report['xg']} xG from {report['shots']} shots, "
                                    f"{report['possession_pct']}% possession; {report['pressures']} pressures "
                                    f"and {report['high_turnovers']} high turnovers (PPDA {report['ppda']})."}])

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
        fallback_reason = "model_unavailable"
        if self.llm.available:
            tool_log: list[str] = []
            text = await self.llm.run("AskTheAnalyst", INSTRUCTIONS, f"[lang={lang}] {question}", timeout=12.0,
                                      tools=self.tools(tool_log))
            if text:
                approved = {a["id"]: a for result in tool_log for a in json.loads(result).get("verified_answers", [])}
                selected = []
                try:
                    ids = json.loads(text).get("answer_ids", [])
                    if isinstance(ids, list) and 0 < len(ids) <= 3 and all(isinstance(i, str) and i in approved for i in ids):
                        selected = [approved[i] for i in dict.fromkeys(ids)]
                except (ValueError, AttributeError):
                    # Exact source text is also accepted for older published agent versions.
                    selected = [a for a in approved.values() if a["answer"] == text.strip()][:1]
                from touchline.safety import safety
                fallback_reason = "unbound_model_answer"
                answer = " ".join(a["answer"] for a in selected)
                if selected and (await safety.moderate(answer))["ok"]:
                    return {"answer": answer, "citations": list(dict.fromkeys(c for a in selected for c in a["citations"])),
                            "source": f"llm:{self.llm.backend}", "language": "en", "composition": "source_rendered_selection",
                            "execution": self.llm.execution() if hasattr(self.llm, "execution") else {},
                            "grounding": {"tool_results": len(tool_log), "numbers_supported": True,
                                          "citations_supported": True, "claims_bound": True,
                                          "scope": "Exact source-rendered statements selected by the model; no free paraphrase."}}
                if selected:
                    fallback_reason = "safety_blocked_or_unavailable"
            else:
                fallback_reason = "model_no_result"
        return {**self.route(question), "language": "en", "requested_language": lang,
                "fallback_reason": fallback_reason,
                "execution": self.llm.execution() if hasattr(self.llm, "execution") else {}}

    def route(self, q: str) -> dict:
        s = self.s
        ql = q.lower()
        h, a = s.meta.home, s.meta.away
        tn = {"home": h.name, "away": a.name}
        if not re.search(r"\bwhy\b", ql) and re.search(r"\b(score|won|winner|result|leading|lead|draw|beat)\b", ql):
            sh, sa = s.score["home"], s.score["away"]
            final = s.status == "full_time"
            if sh == sa:
                result = f"The match {'ended level' if final else 'is level'} at {sh}-{sa}."
            else:
                winner, loser = (h.name, a.name) if sh > sa else (a.name, h.name)
                result = f"{winner} {'beat' if final else 'lead'} {loser} {max(sh, sa)}-{min(sh, sa)}."
            return {"answer": f"{'Full time' if final else str(s.minute) + chr(39)}: {h.name} {sh}-{sa} {a.name}. {result}",
                    "citations": [e.id for e in s.events.values() if e.type == "goal"], "source": "router"}
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
            ins = [i for i in self.insights() if (want is None or i["kind"] == want)
                   and i.get("verification", {}).get("status") == "verified"]
            if ins:
                i = ins[-1]
                r = self._source_copy(i)
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
