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
For real Premier League history, career/season achievements, all-time or world records,
call get_source_scope and select its source_scope answer. Synthetic match facts cannot
establish real-world historical records. Do not answer a historical-record question with
an unrelated goal or player statistic; include the explicit source limitation first.
If the requested fact is unavailable, return {"answer_ids":[]}. Language availability is explicit
in each record; never label an English answer as another language."""

SOURCE_SCOPE = ("This is a synthetic match with fictional clubs and players. Its event feed cannot establish "
                "real Premier League, career, all-time or world records. I can report only facts and "
                "within-match records from this simulated match.")


def needs_source_scope(question: str) -> bool:
    """A bounded intent guard, not a general natural-language relevance classifier."""
    return bool(re.search(r"\ball[ -]time\b|\bworld\s+record|\bleague\s+record|\bpremier\s+league\b|"
                          r"\bcareer\b|\b(?:this|last|previous|entire)\s+season\b", question, re.I))


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
                                          "citations": a.get("citations", []), "language": "en",
                                          "answer_type": a.get("answer_type", "match_fact")}
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

        def get_source_scope() -> str:
            """Source limitations: fictional synthetic match; cannot establish real Premier League, career, season or world records."""
            return record({"synthetic": True, "historical_data_available": False},
                          [{"answer": SOURCE_SCOPE, "answer_type": "source_scope"}])

        return [get_scoreboard, get_player_stats, list_key_moments, explain_event, get_events, get_team_report, get_source_scope]

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
        model_attempt = None
        tool_log: list[str] = []
        if self.llm.available:
            text = await self.llm.run("AskTheAnalyst", INSTRUCTIONS, f"[lang={lang}] {question}", timeout=12.0,
                                      tools=self.tools(tool_log))
            model_attempt = self.llm.execution() if hasattr(self.llm, "execution") else {}
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
                if needs_source_scope(question) and selected and not any(a.get("answer_type") == "source_scope" for a in selected):
                    selected = []
                    fallback_reason = "source_scope_missing"
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
                "composition": "deterministic_source_route",
                "grounding": {"tool_results": len(tool_log), "tool_results_accepted": 0,
                              "scope": "The application rendered this answer from match data or verified story frames. No model answer was accepted."},
                "execution": {"path": "application_fallback", "completed": True, "fallback": True,
                              "fallback_reason": fallback_reason, "model_attempted": model_attempt is not None,
                              "model_attempt": model_attempt}}

    def _player_memory(self, player, recovery: bool) -> dict:
        """Use existing checked story frames, never a free-form causal explanation."""
        from touchline.agents.narrator import _render_frame
        keys = {"s.redemption", "s.error"} if recovery else {"s.redemption", "s.error", "s.duel", "s.keeper", "s.waste"}
        matches = []
        for ins in self.insights():
            if ins.get("verification", {}).get("status") != "verified":
                continue
            for frame in ins.get("reasons", []):
                if (frame.get("k") in keys and player.name in frame.get("p", {}).values()
                        and frame.get("ev") and all(eid in self.s.events for eid in frame["ev"])):
                    matches.append((ins, frame))
        # An error by itself does not establish recovery; don't accept the question's premise.
        if not matches or (recovery and not any(fr["k"] == "s.redemption" for _, fr in matches)):
            scope = "recovery storyline" if recovery else "player storyline"
            return {"answer": f"I don't have a verified {scope} for {player.name} in the available match insights. "
                              "I can't confirm the linked sequence described in the question.",
                    "citations": [], "source": "router", "answer_type": "story_unavailable"}
        if recovery:
            redemption = next(pair for pair in reversed(matches) if pair[1]["k"] == "s.redemption")
            # Only pair the callback with the same cited possession loss, not an unrelated later error.
            errors = [pair for pair in matches if pair[1]["k"] == "s.error"
                      and pair[1]["ev"][0] == redemption[1]["ev"][0]]
            matches = errors[-1:] + [redemption]
        else:
            matches = matches[-3:]
        lines, citations = [], []
        for ins, frame in matches:
            lines.append(f"{ins['minute']}': {_render_frame(ins['headline'], 'en', 'analyst')} — "
                         + _render_frame(frame, "en", "analyst"))
            citations.extend(ins["headline"].get("ev", []))
            citations.extend(frame["ev"])
        return {"answer": " ".join(lines), "citations": list(dict.fromkeys(citations)),
                "source": "router", "answer_type": "verified_player_story"}

    def route(self, q: str) -> dict:
        s = self.s
        ql = q.lower()
        if needs_source_scope(q):
            return {"answer": SOURCE_SCOPE, "citations": [], "source": "router", "answer_type": "source_scope"}
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
                recovery = bool(re.search(r"\brecover(?:ed|y)?\b|\bredemption\b|\bredeem(?:ed)?\b|\bbounc(?:e|ed) back\b", ql))
                memory = bool(re.search(r"\bstory(?:line)?\b|\bremember\b|\blinked (?:match )?events\b|\bpossession loss\b", ql))
                if recovery or memory:
                    return self._player_memory(p, recovery)
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
