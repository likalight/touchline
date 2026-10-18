"""Incremental match state: the shared 'blackboard' every agent reads from.

`MatchState.apply(event)` is O(players) per event and returns an `Enriched` record
with every derived metric the downstream agents need (xG, pass difficulty, xT,
opponents bypassed, win-probability before/after, momentum, control-vs-chaos phase,
player speed, etc.). All numbers are deterministic, so they can be audited.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from touchline.analytics.models import fx, get_models, opponents_bypassed
from touchline.schema import PITCH_L, PITCH_W, Event, MatchMeta

PRIOR_GOALS_90 = 1.45
MOMENTUM_HALF_LIFE = 150.0  # seconds
PHASE_WINDOW = 300.0  # seconds
SPRINT_KMH = 28.0
LONG_CARRY_M = 16.0


def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def win_probability(score_h: int, score_a: int, lam_h: float, lam_a: float) -> dict[str, float]:
    """P(home win / draw / away win) from remaining expected goals (independent Poissons)."""
    ph = [poisson_pmf(k, lam_h) for k in range(11)]
    pa = [poisson_pmf(k, lam_a) for k in range(11)]
    hw = d = aw = 0.0
    for i, p in enumerate(ph):
        for j, q in enumerate(pa):
            fh, fa = score_h + i, score_a + j
            if fh > fa:
                hw += p * q
            elif fh == fa:
                d += p * q
            else:
                aw += p * q
    s = hw + d + aw
    return {"home": hw / s, "draw": d / s, "away": aw / s}


def pitch_control(frame: dict[str, list[float]], pace: dict[str, float], nx: int = 21, ny: int = 14) -> dict:
    """Simplified time-to-intercept pitch control (Spearman-style, closed form)."""
    grid = []
    home_share = 0.0
    third = {"home": 0.0, "away": 0.0}
    n_third = 0
    for i in range(nx):
        x = (i + 0.5) * PITCH_L / nx
        row = []
        for j in range(ny):
            y = (j + 0.5) * PITCH_W / ny
            th = ta = 1e9
            for pid, (px, py) in frame.items():
                t = 0.7 + math.hypot(px - x, py - y) / pace.get(pid, 7.5)
                if pid[0] == "h":
                    th = min(th, t)
                else:
                    ta = min(ta, t)
            c = 1 / (1 + math.exp(-(ta - th) / 0.45))
            row.append(round(c, 2))
            home_share += c
            if x > PITCH_L * 2 / 3:
                third["home"] += c
                n_third += 1
            if x < PITCH_L / 3:
                third["away"] += 1 - c
        grid.append(row)
    return {
        "grid": grid, "nx": nx, "ny": ny,
        "home_share": round(home_share / (nx * ny), 3),
        "home_final_third": round(third["home"] / max(n_third, 1), 3),
        "away_final_third": round(third["away"] / max(n_third, 1), 3),
    }


@dataclass
class Enriched:
    ev: Event
    player_name: Optional[str] = None
    target_name: Optional[str] = None
    xg: Optional[float] = None
    xg_features: Optional[dict] = None
    pass_prob: Optional[float] = None
    difficulty: Optional[float] = None
    pass_features: Optional[dict] = None
    xt_added: float = 0.0
    bypassed: int = 0
    progressive: bool = False
    wp_before: dict = field(default_factory=dict)
    wp_after: dict = field(default_factory=dict)
    momentum: float = 0.0
    phase: str = "balanced"
    possession_change: bool = False
    sequence_len: int = 0
    speed_tags: list = field(default_factory=list)
    milestones: list = field(default_factory=list)

    def facts(self) -> dict:
        """Flat, citable facts about this event (used as evidence by agents)."""
        e = self.ev
        f = {"event_id": e.id, "minute": e.minute, "type": e.type, "team": e.team, "player": self.player_name,
             "outcome": e.outcome}
        if self.target_name:
            f["target"] = self.target_name
        for k in ("distance_m", "ball_speed_kmh", "shot_speed_kmh", "speed_kmh", "pass_type", "body_part"):
            if k in e.qualifiers:
                f[k] = e.qualifiers[k]
        if self.xg is not None:
            f["xg"] = round(self.xg, 2)
        if self.difficulty is not None:
            f["pass_difficulty"] = round(self.difficulty * 100)
            f["pass_completion_prob"] = round(self.pass_prob * 100)
        if self.bypassed:
            f["opponents_bypassed"] = self.bypassed
        if abs(self.xt_added) >= 0.005:
            f["xt_added"] = round(self.xt_added, 3)
        if self.wp_before:
            f["win_prob_before"] = {k: round(v * 100) for k, v in self.wp_before.items()}
            f["win_prob_after"] = {k: round(v * 100) for k, v in self.wp_after.items()}
        return f


def _new_team():
    return defaultdict(float)


class MatchState:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.models = get_models()
        self.players = {p.id: p for p in meta.home.players + meta.away.players}
        self.pace = {pid: p.pace for pid, p in self.players.items()}
        self.t = 0.0
        self.minute = 0
        self.period = 1
        self.score = {"home": 0, "away": 0}
        self.status = "pre"
        self.team: dict[str, defaultdict] = {"home": _new_team(), "away": _new_team()}
        self.pl: dict[str, defaultdict] = {pid: defaultdict(float) for pid in self.players}
        self.heat: dict[str, list[list[int]]] = {pid: [[0] * 8 for _ in range(12)] for pid in self.players}
        self.possession: Optional[str] = None
        self.poss_since = 0.0
        self.seq_len = 0
        self.seq_team: Optional[str] = None
        self.sequences: deque = deque(maxlen=400)
        self.mom = {"home": 0.0, "away": 0.0}
        self.last_mom_t = 0.0
        self.recent: deque = deque()  # (t, team, kind) for phase window
        self.reds = {"home": 0, "away": 0}
        self.records: dict[str, dict] = {}
        self.timeline: list[dict] = []
        self.events: dict[str, Event] = {}
        self.enriched: dict[str, Enriched] = {}
        self.last_frame: Optional[dict] = None
        self.last_frame_t = 0.0
        self.wp = win_probability(0, 0, PRIOR_GOALS_90, PRIOR_GOALS_90 * 0.92)
        self._last_timeline_min = -1

    # ------------------------------------------------------------ derived
    def name(self, pid: Optional[str]) -> Optional[str]:
        return self.players[pid].name if pid in self.players else None

    def remaining_lambda(self) -> tuple[float, float]:
        elapsed = max(self.t / 60, 1.0)
        remaining = max(0.0, (93 if self.period == 2 else 93) - self.t / 60)
        w = max(0.4, 1 - elapsed / 90)
        lam = {}
        for s in ("home", "away"):
            prior = PRIOR_GOALS_90 * (1.06 if s == "home" else 0.94) / 90
            obs = self.team[s]["xg"] / elapsed
            r = w * prior + (1 - w) * obs
            r *= 0.78 ** self.reds[s] * 1.18 ** self.reds["away" if s == "home" else "home"]
            lam[s] = r * remaining
        return lam["home"], lam["away"]

    def momentum_index(self) -> float:
        h, a = self.mom["home"], self.mom["away"]
        return (h - a) / (h + a + 0.02)

    def phase(self) -> dict:
        """Control vs chaos over the last five minutes."""
        while self.recent and self.recent[0][0] < self.t - PHASE_WINDOW:
            self.recent.popleft()
        mins = max(min(self.t, PHASE_WINDOW) / 60, 1)
        turnovers = sum(1 for r in self.recent if r[2] == "turnover") / mins
        duels = sum(1 for r in self.recent if r[2] == "duel") / mins
        passes = {s: sum(1 for r in self.recent if r[2] == "pass" and r[1] == s) for s in ("home", "away")}
        seqs = [s for s in self.sequences if s["end_t"] >= self.t - PHASE_WINDOW]
        avg_seq = sum(s["passes"] for s in seqs) / len(seqs) if seqs else 0
        # chaos index: 0.5 ~ league-typical; calibrated on the synthetic league distribution
        chaos = min(1.0, max(0.0, 0.5 + (turnovers - 2.4) / 2.4 * 0.6 + (3.2 - avg_seq) / 3.2 * 0.4 if seqs else 0.5))
        tot = passes["home"] + passes["away"]
        share = passes["home"] / tot if tot else 0.5
        if turnovers >= 3.0 and avg_seq < 3.0:
            label = "chaos"
        elif share >= 0.62 or (share >= 0.58 and avg_seq >= 4.0):
            label = "home_control"
        elif share <= 0.38 or (share <= 0.42 and avg_seq >= 4.0):
            label = "away_control"
        else:
            label = "balanced"
        return {"label": label, "chaos": round(chaos, 2), "turnovers_per_min": round(turnovers, 2),
                "avg_passes_per_possession": round(avg_seq, 1), "home_pass_share": round(share, 2)}

    def ppda(self, side: str) -> Optional[float]:
        """Opposition passes allowed per defensive action in the opponent's 60% of the pitch."""
        d = self.team[side]["high_def_actions"]
        o = self.team["away" if side == "home" else "home"]["passes_own_60"]
        return round(o / d, 1) if d else None

    def possession_pct(self) -> dict:
        h, a = self.team["home"]["poss_time"], self.team["away"]["poss_time"]
        tot = h + a
        return {"home": round(100 * h / tot) if tot else 50, "away": round(100 * a / tot) if tot else 50}

    # ------------------------------------------------------------ ingest
    def _possession(self, side: Optional[str], ev: Event) -> bool:
        if side is None:
            return False
        if self.possession is not None:
            self.team[self.possession]["poss_time"] += max(0.0, ev.t - self.poss_since)
        self.poss_since = ev.t
        changed = side != self.possession
        if changed:
            if self.seq_team is not None:
                self.sequences.append({"team": self.seq_team, "passes": self.seq_len, "end_t": ev.t})
                if self.possession is not None and ev.type in ("interception", "tackle"):
                    self.recent.append((ev.t, side, "turnover"))
            self.possession = side
            self.seq_team = side
            self.seq_len = 0
        return changed

    def _decay_momentum(self, t: float) -> None:
        dt = max(0.0, t - self.last_mom_t)
        f = 0.5 ** (dt / MOMENTUM_HALF_LIFE)
        for s in self.mom:
            self.mom[s] *= f
        self.last_mom_t = t

    def _record(self, key: str, value: float, ev: Event, pid: Optional[str], higher=True) -> bool:
        cur = self.records.get(key)
        if cur is None or (value > cur["value"] if higher else value < cur["value"]):
            self.records[key] = {"value": value, "event_id": ev.id, "player": self.name(pid), "minute": ev.minute}
            return cur is not None
        return False

    def apply(self, ev: Event) -> Enriched:
        m = self.models
        self.events[ev.id] = ev
        en = Enriched(ev=ev, player_name=self.name(ev.player_id), target_name=self.name(ev.target_id))
        en.wp_before = dict(self.wp)
        self._decay_momentum(ev.t)
        self.t, self.minute, self.period = ev.t, ev.minute, ev.period
        if ev.type == "kickoff" and self.status == "pre":
            self.status = "live"
        side = ev.team
        T = self.team[side] if side else None
        P = self.pl[ev.player_id] if ev.player_id in self.pl else None

        # player movement from tracking snapshots (speed + distance)
        if ev.frame and self.last_frame and ev.t > self.last_frame_t:
            dt = ev.t - self.last_frame_t
            for pid, (x, y) in ev.frame.items():
                px, py = self.last_frame.get(pid, (x, y))
                d = math.hypot(x - px, y - py)
                if d / dt <= 10.8:  # physically plausible only
                    self.pl[pid]["distance_m"] += d
        if ev.frame:
            self.last_frame, self.last_frame_t = ev.frame, ev.t
            if ev.player_id in self.heat and ev.x is not None:
                i = min(11, int(fx(ev.x, side) / PITCH_L * 12))
                j = min(7, int((ev.y if side == "home" else PITCH_W - ev.y) / PITCH_W * 8))
                self.heat[ev.player_id][i][j] += 1
        if P is not None and ev.type not in ("pressure",):
            P["touches"] += 1

        possessing = side if ev.type in ("pass", "carry", "dribble", "shot", "kickoff", "corner", "interception") else None
        if ev.type == "tackle" and ev.outcome == "won":
            possessing = side
        en.possession_change = self._possession(possessing, ev) and ev.type in ("interception", "tackle")

        if ev.type == "pass":
            T["passes"] += 1
            P["passes"] += 1
            p, feats = m.pass_complete_prob(ev)
            en.pass_prob, en.difficulty, en.pass_features = p, 1 - p, feats
            P["difficulty_sum"] += 1 - p
            P["xp_sum"] += p
            if fx(ev.x, side) < PITCH_L * 0.6:
                T["passes_own_60"] += 1
            self.recent.append((ev.t, side, "pass"))
            if ev.outcome == "complete":
                T["completed"] += 1
                P["completed"] += 1
                self.seq_len += 1
                en.xt_added = m.xt_added(ev)
                en.bypassed = opponents_bypassed(ev)
                prog = fx(ev.end_x, side) - fx(ev.x, side)
                en.progressive = prog >= max(15.0, 0.33 * (PITCH_L - fx(ev.x, side))) and fx(ev.end_x, side) > 52.5
                if en.progressive:
                    T["progressive"] += 1
                    P["progressive"] += 1
                if en.bypassed >= 5 and prog >= 18:
                    T["line_breaks"] += 1
                    P["line_breaks"] += 1
                d = ev.qualifiers.get("distance_m", 0)
                self._record("longest_pass_m", d, ev, ev.player_id)
                if 1 - p >= 0.5:
                    P["hard_completed"] += 1
                if self.pl[ev.target_id] is not None:
                    self.pl[ev.target_id]["received"] += 1
            self._record("fastest_pass_kmh", ev.qualifiers.get("ball_speed_kmh", 0), ev, ev.player_id)
        elif ev.type in ("carry", "dribble"):
            spd = ev.qualifiers.get("speed_kmh", 0)
            dist = ev.qualifiers.get("distance_m", 0)
            if ev.outcome == "success":
                en.xt_added = m.xt_added(ev)
                en.bypassed = opponents_bypassed(ev)
                if ev.type == "dribble":
                    P["dribbles_won"] += 1
            else:
                self.recent.append((ev.t, side, "duel"))
            if spd > P["top_speed_kmh"]:
                P["top_speed_kmh"] = spd
            self._record("top_speed_kmh", spd, ev, ev.player_id)
            if spd >= SPRINT_KMH and dist >= 8 and ev.outcome == "success":
                en.speed_tags.append({"kind": "sprint", "player": en.player_name, "speed_kmh": spd})
            if spd >= SPRINT_KMH:
                P["sprints"] += 1
            if dist >= LONG_CARRY_M and ev.outcome == "success":
                en.speed_tags.append({"kind": "long_carry", "player": en.player_name, "distance_m": dist, "speed_kmh": spd})
        elif ev.type == "shot":
            xg, feats = m.shot_xg(ev)
            en.xg, en.xg_features = xg, feats
            T["shots"] += 1
            T["xg"] += xg
            P["shots"] += 1
            P["xg"] += xg
            if ev.outcome in ("goal", "saved"):
                T["on_target"] += 1
            if xg >= 0.3:
                T["big_chances"] += 1
            spd = ev.qualifiers.get("shot_speed_kmh", 0)
            self._record("fastest_shot_kmh", spd, ev, ev.player_id)
            # credit the creator (key pass) = previous completed pass to this shooter
            prev = self._last_pass_to(ev.player_id)
            if prev:
                self.pl[prev.player_id]["key_passes"] += 1
                self.pl[prev.player_id]["xa"] += xg
        elif ev.type == "goal":
            self.score[side] += 1
            P["goals"] += 1
            prev = self._last_pass_to(ev.player_id, window=20)
            if prev:
                self.pl[prev.player_id]["assists"] += 1
                en.milestones.append({"kind": "assist", "player": self.name(prev.player_id), "event_id": prev.id})
            g = P["goals"]
            if g == 2:
                en.milestones.append({"kind": "brace", "player": en.player_name})
            elif g == 3:
                en.milestones.append({"kind": "hat_trick", "player": en.player_name})
            if self.score[side] == 1 and self.score["away" if side == "home" else "home"] == 0:
                en.milestones.append({"kind": "opener", "team": side})
        elif ev.type == "save":
            P["saves"] += 1
            if P["saves"] in (4, 6, 8):
                en.milestones.append({"kind": "saves", "player": en.player_name, "count": int(P["saves"])})
        elif ev.type in ("tackle", "interception"):
            if ev.outcome in ("won", None):
                T["def_actions"] += 1
                P["tackles" if ev.type == "tackle" else "interceptions"] += 1
                if ev.x is not None and fx(ev.x, side) > PITCH_L * 0.4:
                    T["high_def_actions"] += 1
                    T["high_turnovers"] += 1 if fx(ev.x, side) > PITCH_L * 0.6 else 0
            self.recent.append((ev.t, side, "duel"))
        elif ev.type == "pressure":
            T["pressures"] += 1
            P["pressures"] += 1
            if ev.x is not None and fx(ev.x, side) > PITCH_L * 0.4:
                T["high_def_actions"] += 0.5
        elif ev.type == "foul":
            T["fouls"] += 1
        elif ev.type == "card":
            T["cards"] += 1
            if ev.outcome in ("red", "second_yellow"):
                self.reds[side] += 1
        elif ev.type == "corner":
            T["corners"] += 1
        elif ev.type == "half_time":
            self.status = "half_time"
        elif ev.type == "full_time":
            self.status = "full_time"
        if ev.type == "kickoff" and self.status == "half_time":
            self.status = "live"

        # momentum = decayed threat generated (xT added + xG)
        if side and (en.xt_added > 0 or en.xg):
            self.mom[side] += max(en.xt_added, 0) + (en.xg or 0) * 0.6
            if P is not None:
                P["xt_added"] += max(en.xt_added, 0)
        if side and en.xt_added and T is not None:
            T["xt"] += max(en.xt_added, 0)
        en.momentum = round(self.momentum_index(), 3)
        en.phase = self.phase()["label"]
        en.sequence_len = self.seq_len

        lam_h, lam_a = self.remaining_lambda()
        if ev.type == "full_time":
            lam_h = lam_a = 0.0
        self.wp = win_probability(self.score["home"], self.score["away"], lam_h, lam_a)
        en.wp_after = dict(self.wp)

        if self.minute != self._last_timeline_min and ev.type not in ("half_time",):
            self._last_timeline_min = self.minute
            self.timeline.append({
                "minute": self.minute, "t": ev.t, "momentum": en.momentum,
                "wp": {k: round(v, 3) for k, v in self.wp.items()},
                "xg": {s: round(self.team[s]["xg"], 2) for s in ("home", "away")},
                "phase": en.phase,
            })
        self.enriched[ev.id] = en
        return en

    def _last_pass_to(self, pid: str, window: int = 4) -> Optional[Event]:
        n = 0
        for eid in reversed(list(self.events.keys())[-30:]):
            e = self.events[eid]
            n += 1
            if e.type == "pass" and e.outcome == "complete" and e.target_id == pid:
                return e
            if n > window:
                break
        return None

    # ------------------------------------------------------------ snapshots
    def team_summary(self, side: str) -> dict:
        T = self.team[side]
        acc = T["completed"] / T["passes"] if T["passes"] else 0
        return {
            "goals": self.score[side], "xg": round(T["xg"], 2), "shots": int(T["shots"]), "on_target": int(T["on_target"]),
            "big_chances": int(T["big_chances"]), "passes": int(T["passes"]), "pass_accuracy": round(acc * 100),
            "progressive_passes": int(T["progressive"]), "line_breaking_passes": int(T["line_breaks"]),
            "xt": round(T["xt"], 2), "pressures": int(T["pressures"]), "tackles_interceptions": int(T["def_actions"]),
            "high_turnovers": int(T["high_turnovers"]), "ppda": self.ppda(side), "corners": int(T["corners"]),
            "fouls": int(T["fouls"]), "cards": int(T["cards"]), "possession": self.possession_pct()[side],
        }

    def player_summary(self, pid: str) -> dict:
        P = self.pl[pid]
        p = self.players[pid]
        acc = P["completed"] / P["passes"] if P["passes"] else None
        diff = P["difficulty_sum"] / P["passes"] if P["passes"] else None
        # passing over expectation: completed - expected completions (positive = better than model)
        poe = (P["completed"] - P["xp_sum"]) if P["passes"] else 0
        return {
            "id": pid, "name": p.name, "number": p.number, "position": p.position, "team": p.team,
            "touches": int(P["touches"]), "passes": int(P["passes"]), "pass_accuracy": round(acc * 100) if acc is not None else None,
            "avg_pass_difficulty": round(diff * 100) if diff is not None else None,
            "hard_passes_completed": int(P["hard_completed"]), "progressive_passes": int(P["progressive"]),
            "line_breaking_passes": int(P["line_breaks"]), "key_passes": int(P["key_passes"]), "xa": round(P["xa"], 2),
            "shots": int(P["shots"]), "xg": round(P["xg"], 2), "goals": int(P["goals"]), "assists": int(P["assists"]),
            "xt_added": round(P["xt_added"], 3), "tackles": int(P["tackles"]), "interceptions": int(P["interceptions"]),
            "pressures": int(P["pressures"]), "saves": int(P["saves"]), "dribbles_won": int(P["dribbles_won"]),
            "top_speed_kmh": round(P["top_speed_kmh"], 1), "sprints": int(P["sprints"]),
            "distance_km": round(P["distance_m"] / 1000, 2), "passes_over_expected": round(poe, 1),
        }

    def player_rating(self, pid: str) -> float:
        """Transparent 0-10 impact rating (sum of threat created + defensive work, scaled)."""
        P = self.pl[pid]
        v = (P["xt_added"] * 6 + P["xg"] * 2 + P["goals"] * 1.2 + P["assists"] * 0.9 + P["xa"] * 1.5
             + (P["tackles"] + P["interceptions"]) * 0.12 + P["saves"] * 0.35 + P["hard_completed"] * 0.05)
        return round(max(4.0, min(10.0, 5.6 + 0.45 * v)), 1)

    def top_players(self, n: int = 3, side: Optional[str] = None) -> list[dict]:
        ids = [pid for pid in self.players if side is None or self.players[pid].team == side]
        ranked = sorted(ids, key=lambda pid: -self.player_rating(pid))
        return [{**self.player_summary(pid), "rating": self.player_rating(pid)} for pid in ranked[:n]]

    def snapshot(self) -> dict:
        return {
            "match_id": self.meta.match_id, "status": self.status, "minute": self.minute, "period": self.period,
            "score": dict(self.score), "possession": self.possession,
            "home": self.team_summary("home"), "away": self.team_summary("away"),
            "win_prob": {k: round(v, 3) for k, v in self.wp.items()},
            "momentum": round(self.momentum_index(), 3), "phase": self.phase(),
            "records": self.records,
        }
