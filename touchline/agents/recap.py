"""RecapWriter - automated half-time / full-time / on-demand recaps.

Finds the match *story* (upset vs deserved win, comeback, late winner), its turning
points (largest win-probability swings), who controlled it (control vs chaos share)
and the standout players, then renders it per persona and language through the same
verified phrase banks as live insights.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from touchline.agents.analyst import F
from touchline.agents.narrator import Narrator, _render_frame
from touchline.analytics.state import MatchState


class RecapWriter:
    name = "RecapWriter"
    role = "Writes automated match recaps from the verified record"

    def __init__(self, state: MatchState, narrator: Narrator):
        self.s = state
        self.narrator = narrator

    def turning_points(self, n: int = 3) -> list[dict]:
        swings = []
        for eid, en in self.s.enriched.items():
            if not en.wp_before or not en.ev.team or en.ev.type in ("full_time",):
                continue
            side = en.ev.team
            d = en.wp_after[side] - en.wp_before[side]
            if abs(d) >= 0.05:
                swings.append((abs(d), en))
        swings.sort(key=lambda r: -r[0])
        out = []
        for _, en in swings[:n]:
            out.append({"event_id": en.ev.id, "minute": en.ev.minute, "player": en.player_name, "team": en.ev.team,
                        "type": en.ev.type, "before": en.wp_before[en.ev.team], "after": en.wp_after[en.ev.team]})
        return sorted(out, key=lambda r: r["minute"])

    def frames(self) -> dict:
        s = self.s
        h, a = s.meta.home, s.meta.away
        sh, sa = s.score["home"], s.score["away"]
        xh, xa = round(s.team["home"]["xg"], 2), round(s.team["away"]["xg"], 2)
        last = list(s.events.values())[-1].id if s.events else None
        ev0 = [last] if last else []
        reasons = []
        if sh != sa:
            win, lose = ("home", "away") if sh > sa else ("away", "home")
            wt, lt = (h, a) if win == "home" else (a, h)
            head = F("rc.lead.win", ev0, winner=wt.name, loser=lt.name, score=f"{max(sh, sa)}-{min(sh, sa)}")
            xw, xl = (xh, xa) if win == "home" else (xa, xh)
            reasons.append(F("rc.upset" if xw < xl else "rc.deserved", ev0, winner=wt.name, xg_w=xw, xg_l=xl))
            goals = [e for e in s.events.values() if e.type == "goal"]
            # comeback: winner trailed at some point
            run = {"home": 0, "away": 0}
            trailed = False
            for g in goals:
                run[g.team] += 1
                if run[win] < run[lose]:
                    trailed = True
            if trailed:
                reasons.append(F("rc.comeback", ev0, team=wt.name))
            win_goals = [g for g in goals if g.team == win]
            if win_goals and win_goals[-1].minute >= 80 and abs(sh - sa) == 1:
                g = win_goals[-1]
                reasons.append(F("rc.late", [g.id], player=s.name(g.player_id), minute=g.minute))
        else:
            head = F("rc.lead.draw", ev0, home=h.name, away=a.name, score=f"{sh}-{sa}")
            reasons.append(F("rc.draw_xg", ev0, xg_h=xh, xg_a=xa))
        tps = self.turning_points(2)
        for tp in tps:
            team = h.name if tp["team"] == "home" else a.name
            reasons.append(F("rc.turning", [tp["event_id"]], minute=tp["minute"], player=tp["player"] or team, team=team,
                             before_pct=round(tp["before"] * 100), after_pct=round(tp["after"] * 100)))
        phases = Counter(p["phase"] for p in s.timeline)
        tot = sum(phases.values()) or 1
        hc, ac = phases.get("home_control", 0), phases.get("away_control", 0)
        side, cnt = ("home", hc) if hc >= ac else ("away", ac)
        reasons.append(F("rc.phase", ev0, ["analyst", "studio"], team=h.name if side == "home" else a.name,
                         control_pct=round(100 * cnt / tot), chaos_pct=round(100 * phases.get("chaos", 0) / tot)))
        best = s.top_players(1)[0]
        reasons.append(F("rc.standout", ev0, player=best["name"], rating=best["rating"], xt_added=best["xt_added"],
                         pass_accuracy=best["pass_accuracy"]))
        rec = s.records
        if "fastest_shot_kmh" in rec and "top_speed_kmh" in rec:
            reasons.append(F("rc.records", [rec["fastest_shot_kmh"]["event_id"], rec["top_speed_kmh"]["event_id"]],
                             ["analyst", "studio"], speed_kmh=rec["fastest_shot_kmh"]["value"], player=rec["fastest_shot_kmh"]["player"],
                             top_kmh=rec["top_speed_kmh"]["value"], top_player=rec["top_speed_kmh"]["player"]))
        return {"id": f"{s.meta.match_id}-recap-{s.minute}", "kind": "recap", "t": s.t, "minute": s.minute, "team": None,
                "salience": 1.0, "event_ids": sorted({i for f in [head] + reasons for i in f["ev"]}),
                "headline": head, "reasons": reasons, "score": dict(s.score), "turning_points": tps,
                "players": s.top_players(3), "home": s.team_summary("home"), "away": s.team_summary("away")}

    def render(self, persona: str = "casual", lang: str = "en", recap: Optional[dict] = None) -> dict:
        rc = recap or self.frames()
        out = self.narrator.render(rc, persona, lang)
        if persona == "casual":
            out["lines"] = out["lines"][:3]
        elif persona == "analyst":
            out["lines"] = [{"text": _render_frame(f, lang, persona), "ev": f["ev"], "k": f["k"]}
                            for f in rc["reasons"] if persona in f["aud"]]
        out["data"] = {k: rc[k] for k in ("turning_points", "players", "home", "away", "score")}
        return out
