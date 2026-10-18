"""TacticalAnalyst - turns a Moment into an explainable, citable Insight.

Output is a language-neutral set of frames. Every number in a frame comes from the
MatchState or the glass-box models and carries the event IDs it was derived from,
so the Verifier can re-derive it and the UI can link each claim to the pitch.
"""
from __future__ import annotations

import math
from typing import Optional

from touchline.agents.scout import Moment, MomentScout
from touchline.analytics.models import fx, fy, get_models
from touchline.analytics.state import SPRINT_KMH, Enriched, MatchState
from touchline.schema import PITCH_L, PITCH_W

ALL = ["casual", "analyst", "studio", "access"]


def F(k: str, ev: list[str] | None = None, aud: list[str] | None = None, **p) -> dict:
    return {"k": k, "p": p, "ev": ev or [], "aud": aud or ALL}


class TacticalAnalyst:
    name = "TacticalAnalyst"
    role = "Explains why a moment matters, citing evidence and counterfactuals"

    def __init__(self, state: MatchState, scout: MomentScout):
        self.s = state
        self.scout = scout
        self.m = get_models()
        self.n = 0
        self.storyline = None  # set by the runtime; story moments are written by the StorylineKeeper

    # ------------------------------------------------------------------ helpers
    def tname(self, side: Optional[str]) -> str:
        if side is None:
            return ""
        return (self.s.meta.home if side == "home" else self.s.meta.away).name

    def pname(self, pid: Optional[str]) -> str:
        return self.s.name(pid) or ""

    def pct(self, v: float) -> int:
        return int(round(v * 100))

    def zone(self, x: float, y: float, side: str) -> dict:
        ax, ay = fx(x, side), fy(y, side)
        if ax > 88.5 and 13.8 < ay < 54.2:
            z = "box"
        elif ax > 70:
            z = "final_third"
        elif ax > 35:
            z = "midfield"
        else:
            z = "own_half"
        sd = "left" if ay > 45 else "right" if ay < 23 else "centre"
        return {"zone": z, "side": sd, "dist_goal": round(math.hypot(PITCH_L - ax, PITCH_W / 2 - ay))}

    def location_frame(self, ev, aud=("access",)) -> dict:
        z = self.zone(ev.x, ev.y, ev.team)
        return F("r.location", [ev.id], list(aud), player=self.pname(ev.player_id), zone=f"@v.zone.{z['zone']}",
                 dist_goal=z["dist_goal"])

    def buildup(self, shot_ev) -> dict:
        """Walk back from a shot to the start of the possession."""
        ids = list(self.s.events.keys())
        i = ids.index(shot_ev.id)
        passes, xt, chain = 0, 0.0, []
        for eid in reversed(ids[max(0, i - 40):i]):
            e = self.s.events[eid]
            if e.team != shot_ev.team and e.type in ("interception", "tackle", "kickoff", "corner", "save"):
                break
            if e.team != shot_ev.team and e.type == "pass":
                break
            if e.team == shot_ev.team and e.type == "pass" and e.outcome == "complete":
                passes += 1
                xt += max(self.s.enriched[eid].xt_added, 0)
                chain.append(eid)
            if e.team == shot_ev.team and e.type in ("carry", "dribble") and e.outcome == "success":
                xt += max(self.s.enriched[eid].xt_added, 0)
                chain.append(eid)
            if e.type in ("kickoff", "corner") and e.team == shot_ev.team:
                chain.append(eid)
                break
        return {"passes": passes, "xt": round(xt, 2), "chain": list(reversed(chain))}

    def assist_of(self, shot_ev):
        ids = list(self.s.events.keys())
        i = ids.index(shot_ev.id)
        for eid in reversed(ids[max(0, i - 4):i]):
            e = self.s.events[eid]
            if e.type == "pass" and e.outcome == "complete" and e.target_id == shot_ev.player_id:
                return e
        return None

    def shot_reasons(self, en: Enriched) -> tuple[list[dict], Optional[dict]]:
        ev = en.ev
        frames = [F("r.chance_quality", [ev.id], xg=round(en.xg, 2), xg_pct=self.pct(en.xg))]
        contrib = self.m.xg.explain(en.xg_features, self.m.shot_baseline)
        if contrib:
            c = contrib[0]
            frames.append(F("r.top_factor", [ev.id], ["analyst", "studio"], factor=f"@v.factor.{c['feature']}",
                            effect="@v.effect.up" if c["logodds"] > 0 else "@v.effect.down"))
        cf = self.m.counterfactual_shot(en.xg_features)
        if cf:
            frames.append(F("r.counterfactual", [ev.id], ["analyst", "casual"], change=f"@v.cf.{cf['change']}",
                            xg_after=cf["xg_after"], xg_after_pct=self.pct(cf["xg_after"]), delta=cf["delta"]))
        return frames, {"xg": round(en.xg, 3), "contributions": contrib, "counterfactual": cf}

    # ------------------------------------------------------------------ main
    def analyse(self, mo: Moment) -> dict:
        self.n += 1
        s = self.s
        ev = s.events[mo.event_ids[-1]]
        en = s.enriched[ev.id]
        reasons: list[dict] = []
        viz: dict = {}
        explain: dict = {}
        k = mo.kind
        team = self.tname(mo.team)
        head: dict

        if k.startswith("story_") and self.storyline is not None:
            head, reasons, viz = self.storyline.frames(mo)
        elif k == "goal":
            shot = s.events[mo.event_ids[0]]
            sen = s.enriched[shot.id]
            head = F("h.goal", [ev.id], player=self.pname(ev.player_id), team=team)
            if sen.xg is not None:
                fr, explain = self.shot_reasons(sen)
                reasons += fr
            a = self.assist_of(shot)
            if a:
                aen = s.enriched[a.id]
                reasons.append(F("r.assist", [a.id], assister=self.pname(a.player_id), difficulty=self.pct(aen.difficulty)))
            b = self.buildup(shot)
            if b["passes"] >= 3:
                reasons.append(F("r.buildup", b["chain"][-6:], passes=b["passes"], xt=b["xt"]))
            wb, wa = en.wp_before[mo.team], en.wp_after[mo.team]
            reasons.append(F("r.wp_swing", [ev.id], team=team, before_pct=self.pct(wb), after_pct=self.pct(wa)))
            ps = s.player_summary(ev.player_id)
            if ps["goals"] >= 2 or ps["goals"] - ps["xg"] >= 0.6:
                key = "r.finishing_over" if ps["goals"] - ps["xg"] >= 0.4 else "r.finishing_under"
                reasons.append(F(key, [ev.id], ["analyst", "studio"], player=ps["name"], goals=ps["goals"], xg=ps["xg"]))
            reasons.append(self.location_frame(shot))
            viz = {"type": "shot", "x": shot.x, "y": shot.y, "end_x": shot.end_x, "end_y": shot.end_y, "xg": round(sen.xg or 0, 2),
                   "chain": b["chain"][-8:], "wp_before": round(wb, 3), "wp_after": round(wa, 3), "team": mo.team}
        elif k in ("chance_saved", "chance_missed", "chance_blocked"):
            keeper = ""
            if k == "chance_saved":
                keeper = self.pname(ev.player_id)
                ev = s.events[mo.event_ids[0]]
                en = s.enriched[ev.id]
            fr, explain = self.shot_reasons(en)
            head = F(f"h.{k}", [ev.id], player=self.pname(ev.player_id), keeper=keeper)
            reasons += fr
            if k == "chance_saved" and ev.qualifiers.get("shot_speed_kmh"):
                reasons.append(F("r.save_speed", [ev.id], ["analyst", "studio", "casual"], shot_speed_kmh=ev.qualifiers["shot_speed_kmh"]))
            ps = s.player_summary(ev.player_id)
            if ps["shots"] >= 3:
                reasons.append(F("r.finishing_under", [ev.id], ["analyst"], player=ps["name"], goals=ps["goals"], xg=ps["xg"]))
            reasons.append(self.location_frame(ev))
            viz = {"type": "shot", "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y, "xg": round(en.xg, 2), "team": mo.team,
                   "outcome": ev.outcome}
        elif k in ("line_break", "hard_pass"):
            head = F(f"h.{k}", [ev.id], player=self.pname(ev.player_id))
            q = ev.qualifiers
            reasons.append(F("r.pass_stats", [ev.id], distance_m=q.get("distance_m"), ball_speed_kmh=q.get("ball_speed_kmh"),
                             difficulty=self.pct(en.difficulty), prob_pct=self.pct(en.pass_prob)))
            if en.bypassed:
                reasons.append(F("r.bypassed", [ev.id], bypassed=en.bypassed))
            xb, xa = self.m.xt(ev.x, ev.y, ev.team), self.m.xt(ev.end_x, ev.end_y, ev.team)
            if en.xt_added > 0.005:
                reasons.append(F("r.xt_gain", [ev.id], ["analyst", "casual", "studio"], xt_before=round(xb, 3), xt_after=round(xa, 3),
                                 xt=round(en.xt_added, 3), xt_mult=max(2, round(xa / max(xb, 0.002)))))
            contrib = self.m.pass_.explain(en.pass_features, self.m.pass_baseline)
            explain = {"pass_completion_prob": round(en.pass_prob, 3), "contributions": contrib}
            viz = {"type": "pass", "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y, "team": mo.team,
                   "difficulty": self.pct(en.difficulty), "bypassed": en.bypassed, "receiver": self.pname(ev.target_id)}
        elif k in ("sprint", "long_carry"):
            q = ev.qualifiers
            if k == "sprint":
                head = F("h.sprint", [ev.id], player=self.pname(ev.player_id), speed_kmh=q.get("speed_kmh"))
                reasons.append(F("r.speed_threshold", [ev.id], threshold_kmh=SPRINT_KMH))
            else:
                head = F("h.long_carry", [ev.id], player=self.pname(ev.player_id), distance_m=q.get("distance_m"))
            reasons.append(F("r.carry_speed", [ev.id], distance_m=q.get("distance_m"), speed_kmh=q.get("speed_kmh")))
            viz = {"type": "player_tag", "player_id": ev.player_id, "name": self.pname(ev.player_id),
                   "number": s.players[ev.player_id].number, "speed_kmh": q.get("speed_kmh"),
                   "distance_m": q.get("distance_m"), "x": ev.end_x, "y": ev.end_y, "team": mo.team}
        elif k == "momentum":
            w = mo.data["window"]
            head = F("h.momentum", [ev.id], team=team)
            reasons.append(F("r.momentum_share", [ev.id], team=team, share_pct=self.pct(mo.data["share"])))
            if w["shots"]:
                reasons.append(F("r.momentum_shots", [ev.id], ["analyst", "studio", "casual"], shots=w["shots"], xg=round(w["xg"], 2)))
            viz = {"type": "momentum", "team": mo.team, "series": s.timeline[-12:]}
        elif k == "phase":
            ph = mo.data
            if ph["label"] == "chaos":
                head = F("h.phase_chaos", [ev.id])
                reasons.append(F("r.phase_turnovers", [ev.id], turnovers_per_min=ph["turnovers_per_min"],
                                 avg_passes=ph["avg_passes_per_possession"]))
            else:
                head = F("h.phase_control", [ev.id], team=team)
                share = ph["home_pass_share"] if mo.team == "home" else round(1 - ph["home_pass_share"], 2)
                reasons.append(F("r.phase_control", [ev.id], team=team, share_pct=self.pct(share)))
                reasons.append(F("r.phase_turnovers", [ev.id], ["analyst"], turnovers_per_min=ph["turnovers_per_min"],
                                 avg_passes=ph["avg_passes_per_possession"]))
            viz = {"type": "phase", "label": ph["label"], "chaos": ph["chaos"], "team": mo.team}
        elif k == "press":
            w = mo.data
            head = F("h.press", [ev.id], team=team)
            reasons.append(F("r.press_actions", [ev.id], pressures=w["pressures"], high_turnovers=w["high_turnovers"]))
            ppda = s.ppda(mo.team)
            if ppda is not None:
                reasons.append(F("r.press_ppda", [ev.id], ["analyst"], ppda=ppda))
            viz = {"type": "press", "team": mo.team, **{k2: w[k2] for k2 in ("pressures", "high_turnovers")}}
        elif k in ("card_yellow", "card_red"):
            head = F(f"h.{k}", [ev.id], player=self.pname(ev.player_id))
            if k == "card_red":
                reasons.append(F("r.card_wp", [ev.id], team=team, before_pct=self.pct(en.wp_before[mo.team]),
                                 after_pct=self.pct(en.wp_after[mo.team])))
            viz = {"type": "card", "card": "red" if k == "card_red" else "yellow", "team": mo.team}
        elif k == "wp_swing":
            head = F("h.wp_swing", [ev.id], team=team)
            reasons.append(F("r.wp_swing", [ev.id], team=team, before_pct=self.pct(en.wp_before[mo.team]),
                             after_pct=self.pct(en.wp_after[mo.team])))
            viz = {"type": "wp", "series": s.timeline[-20:]}
        elif k in ("brace", "hat_trick"):
            head = F(f"h.{k}", [ev.id], player=self.pname(ev.player_id))
            ps = s.player_summary(ev.player_id)
            reasons.append(F("r.finishing_over" if ps["goals"] > ps["xg"] else "r.finishing_under", [ev.id],
                             player=ps["name"], goals=ps["goals"], xg=ps["xg"]))
            viz = {"type": "player_card", "player": ps, "team": mo.team}
        elif k == "saves":
            head = F("h.saves", [ev.id], player=self.pname(ev.player_id), count=mo.data["count"])
            viz = {"type": "player_card", "player": s.player_summary(ev.player_id), "team": mo.team}
        elif k == "record_shot":
            head = F("h.record_shot", [ev.id], speed_kmh=ev.qualifiers.get("shot_speed_kmh"))
            reasons.append(F("r.record", [ev.id]))
            reasons.append(self.location_frame(ev, ALL))
            viz = {"type": "shot", "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y, "team": mo.team,
                   "xg": round(en.xg or 0, 2), "outcome": ev.outcome}
        elif k == "rhythm":
            trend = "up" if mo.data["cur"] > mo.data["prev"] else "down"
            head = F("h.rhythm", [ev.id], trend=f"@v.trend.{trend}")
            reasons.append(F("r.rhythm", [ev.id], events_per_min=mo.data["cur"], prev_per_min=mo.data["prev"]))
            viz = {"type": "rhythm", "cur": mo.data["cur"], "prev": mo.data["prev"]}
        elif k == "standout":
            p = mo.data["player"]
            head = F("h.standout", [ev.id], player=p["name"])
            reasons.append(F("r.player_line", [ev.id], rating=p["rating"], passes=p["passes"], pass_accuracy=p["pass_accuracy"],
                             xt_added=p["xt_added"], tackles=p["tackles"], touches=p["touches"]))
            viz = {"type": "player_card", "player": p, "team": p["team"]}
        elif k in ("half_time", "full_time"):
            h, a = s.meta.home, s.meta.away
            head = F(f"h.{k}", [ev.id], home=h.name, away=a.name, score_home=s.score["home"], score_away=s.score["away"])
            reasons.append(F("r.recap_xg", [ev.id], home=h.short, away=a.short, xg_home=round(s.team["home"]["xg"], 2),
                             xg_away=round(s.team["away"]["xg"], 2)))
            pp = s.possession_pct()
            reasons.append(F("r.recap_poss", [ev.id], poss_home=pp["home"], poss_away=pp["away"]))
            viz = {"type": "summary", "home": s.team_summary("home"), "away": s.team_summary("away")}
        else:
            head = F("h.focus_touch", [ev.id], player=self.pname(ev.player_id), action=k)

        evidence = sorted({i for f in [head] + reasons for i in f["ev"]})
        return {
            "id": f"{s.meta.match_id}-I{self.n:04d}",
            "kind": k, "t": mo.t, "minute": mo.minute, "team": mo.team, "player_id": mo.player_id,
            "salience": round(min(1.0, mo.salience), 2),
            "event_ids": evidence, "headline": head, "reasons": reasons, "explain": explain, "viz": viz,
            "score": dict(s.score), "wp": {kk: round(v, 3) for kk, v in s.wp.items()},
        }

    def _next(self, ev, typ):
        ids = list(self.s.events.keys())
        i = ids.index(ev.id)
        for eid in ids[i + 1:i + 3]:
            if self.s.events[eid].type == typ:
                return self.s.events[eid]
        return None
