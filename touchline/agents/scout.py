"""MomentScout - decides which moments deserve airtime.

Each candidate gets a salience score in [0, 1]. Cool-downs stop the screen from
flooding; sustained-state detectors (momentum, control vs chaos, pressing spells,
rhythm) only fire once a pattern has held, not on single noisy events.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from touchline.analytics.models import fx
from touchline.analytics.state import Enriched, MatchState
from touchline.schema import PITCH_L

WINDOW = 300.0


@dataclass
class Moment:
    kind: str
    salience: float
    t: float
    minute: int
    team: Optional[str]
    event_ids: list[str]
    player_id: Optional[str] = None
    data: dict = field(default_factory=dict)


class MomentScout:
    name = "MomentScout"
    role = "Detects candidate moments and scores their salience"

    COOLDOWN = {  # match-seconds between two moments of the same kind
        "line_break": 120, "hard_pass": 150, "sprint": 240, "long_carry": 360, "momentum": 600,
        "phase": 360, "press": 420, "rhythm": 600, "standout": 1200, "record_shot": 60, "wp_swing": 180,
    }

    def __init__(self, state: MatchState):
        self.s = state
        self.window: deque = deque()
        self.last_kind: dict[str, float] = {}
        self.last_any = -999.0
        self.mom_side: Optional[str] = None
        self.mom_since = 0.0
        self.phase_label = "balanced"
        self.phase_candidate = "balanced"
        self.phase_since = 0.0
        self.rhythm_marks: list[tuple[float, int]] = []
        self.standout_done: set[int] = set()
        self.press_side: Optional[str] = None
        self.n_events = 0

    # ------------------------------------------------------------------ window helpers
    def _push(self, en: Enriched) -> None:
        e = en.ev
        self.window.append((e.t, e.team, max(en.xt_added, 0), en.xg or 0.0, e.type, e.x, e.outcome))
        while self.window and self.window[0][0] < e.t - WINDOW:
            self.window.popleft()

    def window_stats(self) -> dict:
        st = {s: {"threat": 0.0, "xg": 0.0, "shots": 0, "pressures": 0, "high_turnovers": 0, "passes": 0}
              for s in ("home", "away")}
        for t, team, xt, xg, typ, x, outcome in self.window:
            if team not in st:
                continue
            d = st[team]
            d["threat"] += xt + 0.6 * xg
            d["xg"] += xg
            if typ == "shot":
                d["shots"] += 1
            if typ == "pressure":
                d["pressures"] += 1
            if typ in ("interception", "tackle") and outcome == "won" and x is not None and fx(x, team) > PITCH_L * 0.6:
                d["high_turnovers"] += 1
            if typ == "pass":
                d["passes"] += 1
        return st

    def _ok(self, kind: str, t: float, gap: float = 25.0) -> bool:
        if t - self.last_any < gap:
            return False
        return t - self.last_kind.get(kind, -1e9) >= self.COOLDOWN.get(kind, 0)

    def _take(self, m: Moment) -> Moment:
        self.last_kind[m.kind] = m.t
        self.last_any = m.t
        return m

    # ------------------------------------------------------------------ main
    def observe(self, en: Enriched) -> list[Moment]:
        e = en.ev
        s = self.s
        self._push(en)
        self.n_events += 1
        out: list[Moment] = []
        t = e.t

        # --- punctual, high-value moments (bypass global gap)
        if e.type == "shot":
            if e.outcome == "goal":
                pass  # handled on the 'goal' event (score updated there)
            elif (en.xg or 0) >= 0.22 and e.outcome != "saved":  # saves are surfaced on the 'save' event
                kind = "chance_blocked" if e.outcome == "blocked" else "chance_missed"
                out.append(self._take(Moment(kind, 0.55 + min(en.xg, 0.6) * 0.6, t, e.minute, e.team, [e.id], e.player_id)))
        if e.type == "save":
            shot = self._prev(e, "shot")
            sx = self.s.enriched[shot.id].xg if shot else 0
            if shot and (sx or 0) >= 0.22:
                out.append(self._take(Moment("chance_saved", 0.55 + min(sx, 0.6) * 0.6, t, e.minute, shot.team,
                                             [shot.id, e.id], shot.player_id)))
            rec = s.records.get("fastest_shot_kmh")
            if rec and rec["event_id"] == e.id and e.minute > 15 and self._ok("record_shot", t, 0):
                out.append(self._take(Moment("record_shot", 0.42, t, e.minute, e.team, [e.id], e.player_id)))
        if e.type == "goal":
            shot = self._prev(e, "shot")
            ids = [shot.id, e.id] if shot else [e.id]
            out.append(self._take(Moment("goal", 1.0, t, e.minute, e.team, ids, e.player_id,
                                         {"milestones": en.milestones})))
            for ms in en.milestones:
                if ms["kind"] in ("brace", "hat_trick"):
                    out.append(Moment(ms["kind"], 0.8, t + 0.1, e.minute, e.team, [e.id], e.player_id))
        if e.type == "card":
            red = e.outcome in ("red", "second_yellow")
            out.append(self._take(Moment("card_red" if red else "card_yellow", 0.85 if red else 0.4, t, e.minute,
                                         e.team, [e.id], e.player_id)))
        if e.type == "save":
            for ms in en.milestones:
                if ms["kind"] == "saves":
                    out.append(Moment("saves", 0.55, t + 0.1, e.minute, e.team, [e.id], e.player_id, {"count": ms["count"]}))
        if e.type in ("half_time", "full_time"):
            out.append(Moment(e.type, 0.95, t, e.minute, None, [e.id]))
            return out

        # --- win-probability swing not caused by a goal (e.g. red cards)
        if e.type not in ("goal",) and en.wp_before and en.wp_after:
            swing = max(abs(en.wp_after[k] - en.wp_before[k]) for k in ("home", "away"))
            if swing >= 0.08 and self._ok("wp_swing", t, 5):
                side = "home" if en.wp_after["home"] - en.wp_before["home"] > 0 else "away"
                out.append(self._take(Moment("wp_swing", 0.65, t, e.minute, side, [e.id], None, {"swing": swing})))

        # --- pass quality & player tagging
        if e.type == "pass" and e.outcome == "complete":
            if en.bypassed >= 5 and en.xt_added >= 0.02 and self._ok("line_break", t):
                out.append(self._take(Moment("line_break", 0.5 + min(en.xt_added, 0.1) * 2, t, e.minute, e.team, [e.id], e.player_id)))
            elif (en.difficulty or 0) >= 0.55 and self._ok("hard_pass", t):
                out.append(self._take(Moment("hard_pass", 0.45 + (en.difficulty - 0.55), t, e.minute, e.team, [e.id], e.player_id)))
        tags = sorted(en.speed_tags, key=lambda tg: tg["kind"] != "sprint")[:1]  # one tag per run, sprint first
        for tag in tags:
            kind = "sprint" if tag["kind"] == "sprint" else "long_carry"
            if self._ok(kind, t):
                out.append(self._take(Moment(kind, 0.38, t, e.minute, e.team, [e.id], e.player_id, dict(tag))))

        # --- sustained patterns (checked every event, but need persistence)
        if t > 360:
            st = self.window_stats()
            tot = st["home"]["threat"] + st["away"]["threat"]
            if tot > 0.12:
                share_h = st["home"]["threat"] / tot
                lead = "home" if share_h >= 0.72 else "away" if share_h <= 0.28 else None
                if lead != self.mom_side:
                    self.mom_side, self.mom_since = lead, t
                elif lead and t - self.mom_since > 60 and self._ok("momentum", t):
                    out.append(self._take(Moment("momentum", 0.6, t, e.minute, lead, [e.id], None,
                                                 {"share": share_h if lead == "home" else 1 - share_h, "window": st[lead]})))
            ph = s.phase()
            if ph["label"] != self.phase_candidate:
                self.phase_candidate, self.phase_since = ph["label"], t
            elif ph["label"] != self.phase_label and t - self.phase_since > 90:
                self.phase_label = ph["label"]
                if ph["label"] != "balanced" and self._ok("phase", t):
                    side = {"home_control": "home", "away_control": "away"}.get(ph["label"])
                    out.append(self._take(Moment("phase", 0.52, t, e.minute, side, [e.id], None, dict(ph))))
            for side in ("home", "away"):
                w = st[side]
                if w["pressures"] >= 6 and w["high_turnovers"] >= 3 and self._ok("press", t):
                    out.append(self._take(Moment("press", 0.5, t, e.minute, side, [e.id], None, dict(w))))
                    break
        # rhythm check every ~10 minutes of match time
        if not self.rhythm_marks or t - self.rhythm_marks[-1][0] >= 600:
            self.rhythm_marks.append((t, self.n_events))
            if len(self.rhythm_marks) >= 3 and self._ok("rhythm", t):
                (t0, n0), (t1, n1), (t2, n2) = self.rhythm_marks[-3:]
                cur = (n2 - n1) / max((t2 - t1) / 60, 1)
                prev = (n1 - n0) / max((t1 - t0) / 60, 1)
                if abs(cur - prev) / max(prev, 1) > 0.12:
                    out.append(self._take(Moment("rhythm", 0.33, t, e.minute, None, [e.id], None,
                                                 {"cur": round(cur, 1), "prev": round(prev, 1)})))
        for mark in (30, 60, 80):
            if e.minute >= mark and mark not in self.standout_done and e.type not in ("goal",):
                self.standout_done.add(mark)
                best = s.top_players(1)[0]
                out.append(self._take(Moment("standout", 0.45, t, e.minute, best["team"], [e.id], best["id"], {"player": best})))
        return out

    def _prev(self, e, typ: str):
        for eid in reversed(list(self.s.events.keys())[-6:]):
            ev = self.s.events[eid]
            if ev.type == typ and ev.id != e.id:
                return ev
        return None
