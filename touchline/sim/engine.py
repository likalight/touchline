"""Synthetic, football-realistic match simulator.

Generates a full 90-minute event stream with a tracking snapshot for every event.
It is a spatial possession model: 22 players hold formation anchors that slide with
the ball and game state; the ball carrier chooses passes, carries, dribbles or shots
based on location, pressure, teammate openness and the scoreline. Fatigue, game-state
urgency and finishing quality create emergent storylines (momentum swings, late
pressure, keepers having a night) rather than scripted ones.

Deterministic for a given seed.
"""
from __future__ import annotations

import math
import random
from typing import Iterator, Optional

from touchline.schema import PITCH_L, PITCH_W, Event, MatchMeta, Player
from touchline.sim.teams import FORMATION_433, anchor, build_team

GOAL_Y = PITCH_W / 2


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def true_goal_prob(dist: float, angle: float, header: bool, pressure: bool,
                   finishing: float, assisted_by_through: bool) -> float:
    """The simulator's hidden 'ground truth' scoring model (analytics never sees it)."""
    z = -0.95 - 0.115 * dist + 1.25 * angle - 0.75 * header - 0.45 * pressure
    z += 1.6 * (finishing - 0.5) + 0.15 * assisted_by_through
    return 1 / (1 + math.exp(-z))


def shot_angle(x: float, y: float, attacking_right: bool) -> float:
    gx = PITCH_L if attacking_right else 0.0
    p1, p2 = (gx, GOAL_Y - 3.66), (gx, GOAL_Y + 3.66)
    a1 = math.atan2(p1[1] - y, p1[0] - x)
    a2 = math.atan2(p2[1] - y, p2[0] - x)
    ang = abs(a1 - a2)
    return ang if ang <= math.pi else 2 * math.pi - ang


class MatchSimulator:
    def __init__(self, seed: int = 7, match_id: Optional[str] = None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.match_id = match_id or f"SYN-{seed:05d}"
        names: set[str] = set()
        self.home = build_team("home", self.rng, names)
        self.away = build_team("away", self.rng, names)
        self.meta = MatchMeta(
            match_id=self.match_id, competition="Synthetic Premier Cup (simulated)",
            venue="Estuary Park (fictional)", home=self.home, away=self.away, seed=seed,
        )
        self.players: dict[str, Player] = {p.id: p for p in self.home.players + self.away.players}
        self.index = {p.id: i for t in (self.home, self.away) for i, p in enumerate(t.players)}
        self.pos: dict[str, list[float]] = {}
        for t in (self.home, self.away):
            for i, p in enumerate(t.players):
                self.pos[p.id] = list(anchor(i, t.side))
        self.t = 0.0
        self.period = 1
        self.seq = 0
        self.score = {"home": 0, "away": 0}
        self.yellows: set[str] = set()
        self.ball = [PITCH_L / 2, GOAL_Y]
        self.possession = "home"
        self.carrier = "h9"
        self.through_flag = False
        # Team "form" drifts during the match -> momentum swings
        self.form = {"home": 0.0, "away": 0.0}

    # ------------------------------------------------------------------ helpers
    def team_of(self, pid: str) -> str:
        return self.players[pid].team

    def opp(self, side: str) -> str:
        return "away" if side == "home" else "home"

    def fx(self, x: float, side: str) -> float:
        """x in the attacking frame of `side`."""
        return x if side == "home" else PITCH_L - x

    def fatigue(self) -> float:
        return _clamp((self.t / 60 - 55) / 35, 0, 1) * 0.12

    def urgency(self, side: str) -> float:
        diff = self.score[side] - self.score[self.opp(side)]
        late = _clamp((self.t / 60 - 60) / 30, 0, 1)
        return _clamp(-diff, -1, 2) * (0.3 + 0.7 * late)

    def squad(self, side: str) -> list[Player]:
        return (self.home if side == "home" else self.away).players

    def nearest_opponent(self, pt, side) -> tuple[str, float]:
        best, bd = None, 1e9
        for p in self.squad(self.opp(side)):
            d = _dist(pt, self.pos[p.id])
            if d < bd:
                best, bd = p.id, d
        return best, bd

    def reshape(self) -> None:
        """Slide every player towards a shape driven by ball location + phase."""
        for side in ("home", "away"):
            in_poss = side == self.possession
            bfx = self.fx(self.ball[0], side)
            push = (bfx - 52.5) * 0.55 + (6 if in_poss else -4) + 5 * self.urgency(side)
            for i, p in enumerate(self.squad(side)):
                ax, ay = FORMATION_433[i][2]
                tx = ax + (push * (0.35 if i == 0 else 1.0))
                tx = _clamp(tx, 3 if i == 0 else 8, 98 if in_poss else 92)
                ty = ay + (self.ball[1] - GOAL_Y) * (0.28 if in_poss else 0.4)
                if in_poss and i in (1, 4, 8, 10):  # width in possession
                    ty = ay + (ay - GOAL_Y) * 0.15
                if side == "away":
                    tx, ty = PITCH_L - tx, PITCH_W - ty
                cur = self.pos[p.id]
                k = 0.55
                cur[0] = _clamp(cur[0] + (tx - cur[0]) * k + self.rng.gauss(0, 1.3), 0.5, PITCH_L - 0.5)
                cur[1] = _clamp(cur[1] + (ty - cur[1]) * k + self.rng.gauss(0, 1.3), 0.5, PITCH_W - 0.5)
        # defenders converge on ball
        dside = self.opp(self.possession)
        dists = sorted(self.squad(dside), key=lambda p: _dist(self.pos[p.id], self.ball))
        for j, p in enumerate(dists[:2]):
            if p.position == "GK" and self.fx(self.ball[0], dside) < 85:
                continue
            cur = self.pos[p.id]
            k = 0.55 if j == 0 else 0.3
            cur[0] += (self.ball[0] - cur[0]) * k
            cur[1] += (self.ball[1] - cur[1]) * k
        self.pos[self.carrier] = [self.ball[0], self.ball[1]]

    def frame(self) -> dict[str, list[float]]:
        return {pid: [round(v[0], 2), round(v[1], 2)] for pid, v in self.pos.items()}

    def emit(self, type_: str, dt: float = 0.0, **kw) -> Event:
        self.seq += 1
        t = self.t
        if self.period == 2:
            t = max(t, 45 * 60)
        ev = Event(
            id=f"E{self.seq:05d}", seq=self.seq, match_id=self.match_id, t=round(t, 2),
            period=self.period, minute=int(t // 60) + 1 if type_ not in ("half_time", "full_time") else int(round(t / 60)),
            type=type_, frame=self.frame() if type_ not in ("half_time", "full_time") else None, **kw,
        )
        self.t += dt
        return ev

    # ------------------------------------------------------------------ restarts
    def kickoff(self, side: str) -> Iterator[Event]:
        self.possession = side
        self.ball = [PITCH_L / 2, GOAL_Y]
        for t in (self.home, self.away):
            for i, p in enumerate(t.players):
                ax, ay = anchor(i, t.side)
                # pull both teams into own half
                if t.side == "home":
                    ax = min(ax * 0.62, 50)
                else:
                    ax = max(PITCH_L - (PITCH_L - ax) * 0.62, 55)
                self.pos[p.id] = [ax, ay]
        self.carrier = f"{side[0]}9"
        self.pos[self.carrier] = [PITCH_L / 2, GOAL_Y]
        yield self.emit("kickoff", 1.0, team=side, player_id=self.carrier, x=self.ball[0], y=self.ball[1])

    def give_ball(self, side: str, x: float, y: float, prefer: Optional[str] = None) -> None:
        self.possession = side
        self.ball = [_clamp(x, 0.5, PITCH_L - 0.5), _clamp(y, 0.5, PITCH_W - 0.5)]
        if prefer:
            self.carrier = prefer
        else:
            self.carrier = min(self.squad(side), key=lambda p: _dist(self.pos[p.id], self.ball)).id
        self.pos[self.carrier] = list(self.ball)

    # ------------------------------------------------------------------ actions
    def choose_action(self) -> str:
        side = self.possession
        bfx = self.fx(self.ball[0], side)
        dy = abs(self.ball[1] - GOAL_Y)
        _, d_opp = self.nearest_opponent(self.ball, side)
        p = self.players[self.carrier]
        if p.position == "GK":
            return "pass"
        if bfx > 86 and dy < 18:
            ps = 0.06 + 0.16 * (bfx - 86) / 19 + 0.04 * self.urgency(side) + 0.08 * p.finishing
            if self.through_flag:
                ps += 0.10
            if self.rng.random() < ps:
                return "shot"
        if bfx > 74 and dy < 26 and self.rng.random() < 0.012 + 0.015 * p.finishing:
            return "shot"  # speculative effort
        r = self.rng.random()
        if d_opp < 2.2 and r < 0.30:
            return "dribble"
        if r < 0.20 + (0.08 if p.position in ("RW", "LW", "RB", "LB") else 0):
            return "carry"
        return "pass"

    def pick_target(self) -> tuple[Player, float]:
        side = self.possession
        cand = []
        bfx = self.fx(self.ball[0], side)
        for p in self.squad(side):
            if p.id == self.carrier:
                continue
            tp = self.pos[p.id]
            d = _dist(self.ball, tp)
            if d < 4 or d > 55:
                continue
            _, open_ = self.nearest_opponent(tp, side)
            prog = self.fx(tp[0], side) - bfx
            w = math.exp(-d / 22) * (0.5 + min(open_, 8) / 6) * math.exp(prog / (30 - 8 * self.urgency(side)))
            if p.position == "GK":
                w *= 0.25 if bfx < 40 else 0.02
            cand.append((p, w, open_))
        if not cand:
            p = min((q for q in self.squad(side) if q.id != self.carrier), key=lambda q: _dist(self.ball, self.pos[q.id]))
            return p, 3.0
        tot = sum(c[1] for c in cand)
        r = self.rng.random() * tot
        for p, w, o in cand:
            r -= w
            if r <= 0:
                return p, o
        return cand[-1][0], cand[-1][2]

    def do_pass(self) -> Iterator[Event]:
        side, passer = self.possession, self.players[self.carrier]
        tgt, openness = self.pick_target()
        start = tuple(self.ball)
        end = list(self.pos[tgt.id])
        # through-ball: lead the receiver into space
        through = False
        if self.fx(end[0], side) > 70 and self.rng.random() < 0.3:
            lead = 6 + self.rng.random() * 8
            end[0] = _clamp(end[0] + (lead if side == "home" else -lead), 1, PITCH_L - 1)
            end[0] = min(end[0], 95.5) if side == "home" else max(end[0], PITCH_L - 95.5)
            through = True
        d = _dist(start, end)
        _, press = self.nearest_opponent(start, side)
        lofted = d > 30 or (through and d > 22)
        crowd = sum(1 for q in self.squad(self.opp(side)) if _dist(self.pos[q.id], end) < 6)
        pk = (passer.passing - self.fatigue() + 0.05 * self.form[side]) * 1.55 - 0.017 * d
        pk -= 0.32 * (press < 2.5) + 0.12 * (crowd >= 2) + 0.22 * through - 0.05 * min(openness, 6)
        pk -= 0.45 * (self.fx(end[0], side) > 88) + 0.25 * (self.fx(end[0], side) > 80)
        p_complete = 1 / (1 + math.exp(-(pk * 2.4)))
        speed = _clamp(10 + d * 0.33 + self.rng.gauss(0, 1.5), 7, 30)  # m/s
        flight = d / speed
        complete = self.rng.random() < p_complete
        q = {"distance_m": round(d, 1), "ball_speed_kmh": round(speed * 3.6, 1),
             "height": "high" if lofted else "ground", "pass_type": "through" if through else ("long" if d > 30 else "short")}
        if self.fx(start[0], side) > 80 and abs(start[1] - GOAL_Y) > 20 and self.fx(end[0], side) > 88:
            q["pass_type"] = "cross"
        if complete:
            ev = self.emit("pass", flight + self.rng.uniform(1.3, 3.6), team=side, player_id=passer.id,
                           x=round(start[0], 2), y=round(start[1], 2), end_x=round(end[0], 2), end_y=round(end[1], 2),
                           outcome="complete", target_id=tgt.id, qualifiers=q)
            yield ev
            self.through_flag = through or q["pass_type"] == "cross"
            self.ball = list(end)
            self.carrier = tgt.id
            self.pos[tgt.id] = list(end)
            self.reshape()
            return
        # failure: interception, or out of play
        self.through_flag = False
        mid = (start[0] + (end[0] - start[0]) * self.rng.uniform(0.45, 1.0),
               start[1] + (end[1] - start[1]) * self.rng.uniform(0.45, 1.0))
        out = lofted and self.rng.random() < 0.35
        ev = self.emit("pass", flight, team=side, player_id=passer.id, x=round(start[0], 2), y=round(start[1], 2),
                       end_x=round(mid[0], 2), end_y=round(mid[1], 2), outcome="out" if out else "intercepted",
                       target_id=tgt.id, qualifiers=q)
        yield ev
        if out:
            yield from self.restart_out(side, mid)
            return
        defender, _ = self.nearest_opponent(mid, side)
        self.pos[defender] = list(mid)
        self.give_ball(self.opp(side), mid[0], mid[1], prefer=defender)
        yield self.emit("interception", self.rng.uniform(0.8, 1.6), team=self.possession, player_id=defender,
                        x=round(mid[0], 2), y=round(mid[1], 2), outcome="won")
        self.reshape()

    def restart_out(self, last_side: str, pt) -> Iterator[Event]:
        x, y = pt
        new = self.opp(last_side)
        # over the byline?
        if self.fx(x, last_side) > 100:
            self.give_ball(new, PITCH_L - 6 if new == "away" else 6, GOAL_Y, prefer=f"{new[0]}1")
            yield self.emit("out", self.rng.uniform(12, 22), team=last_side, x=round(x, 2), y=round(y, 2), outcome="goal_kick")
        else:
            yy = 0.5 if y < GOAL_Y else PITCH_W - 0.5
            self.give_ball(new, _clamp(x, 2, PITCH_L - 2), yy)
            yield self.emit("out", self.rng.uniform(8, 16), team=last_side, x=round(x, 2), y=round(yy, 2), outcome="throw_in")
        self.reshape()

    def do_carry(self, dribble: bool = False) -> Iterator[Event]:
        side, p = self.possession, self.players[self.carrier]
        sign = 1 if side == "home" else -1
        length = self.rng.uniform(3, 9) if dribble else self.rng.uniform(4, 16) * (1.15 if p.pace > 9 else 1)
        start = tuple(self.ball)
        end = [_clamp(start[0] + sign * length * self.rng.uniform(0.6, 1.0), PITCH_L - 96, 96),
               _clamp(start[1] + self.rng.gauss(0, 4) + (GOAL_Y - start[1]) * 0.15, 1, PITCH_W - 1)]
        d = _dist(start, end)
        speed = _clamp(p.pace * self.rng.uniform(0.55, 0.92) * (1 - self.fatigue()), 3, 10.5)
        defender, dd = self.nearest_opponent(start, side)
        if defender and dd < 4.5 and self.rng.random() < 0.55:
            yield self.emit("pressure", 0.4, team=self.opp(side), player_id=defender,
                            x=round(self.pos[defender][0], 2), y=round(self.pos[defender][1], 2), target_id=p.id)
        if dribble or dd < 3:
            dfn = self.players[defender]
            p_win = 0.42 + 0.22 * (self.fx(start[0], side) > 85) + 0.35 * (dfn.defending - 0.5) - 0.25 * (p.pace - 8.5) / 1.5 + 0.06 * self.fatigue() * 5
            if self.rng.random() < _clamp(p_win, 0.15, 0.7):
                foul = self.rng.random() < 0.13
                yield self.emit("dribble" if dribble else "carry", d / speed, team=side, player_id=p.id,
                                x=round(start[0], 2), y=round(start[1], 2), end_x=round(start[0] + (end[0] - start[0]) * 0.4, 2),
                                end_y=round(start[1] + (end[1] - start[1]) * 0.4, 2), outcome="lost",
                                qualifiers={"distance_m": round(d * 0.4, 1), "speed_kmh": round(speed * 3.6, 1)})
                self.pos[defender] = list(self.ball)
                yield self.emit("tackle", 1.0, team=self.opp(side), player_id=defender, x=round(self.ball[0], 2),
                                y=round(self.ball[1], 2), target_id=p.id, outcome="foul" if foul else "won")
                if foul:
                    yield from self.foul(defender, p.id)
                else:
                    self.give_ball(self.opp(side), self.ball[0], self.ball[1], prefer=defender)
                    self.reshape()
                return
        yield self.emit("dribble" if dribble else "carry", d / speed, team=side, player_id=p.id,
                        x=round(start[0], 2), y=round(start[1], 2), end_x=round(end[0], 2), end_y=round(end[1], 2),
                        outcome="success", qualifiers={"distance_m": round(d, 1), "speed_kmh": round(speed * 3.6, 1)})
        self.ball = end
        self.pos[p.id] = list(end)
        self.reshape()

    def foul(self, offender: str, victim: str) -> Iterator[Event]:
        side_off = self.team_of(offender)
        yield self.emit("foul", 2.0, team=side_off, player_id=offender, x=round(self.ball[0], 2), y=round(self.ball[1], 2), target_id=victim)
        if self.rng.random() < 0.22:
            card = "red" if offender in self.yellows else "yellow"
            self.yellows.add(offender)
            if card == "red":
                card = "second_yellow"
            yield self.emit("card", 25.0, team=side_off, player_id=offender, outcome=card,
                            x=round(self.ball[0], 2), y=round(self.ball[1], 2))
        self.give_ball(self.opp(side_off), self.ball[0], self.ball[1], prefer=victim)
        self.t += self.rng.uniform(8, 18)
        self.reshape()

    def do_shot(self) -> Iterator[Event]:
        side, p = self.possession, self.players[self.carrier]
        attacking_right = side == "home"
        x, y = self.ball
        gx = PITCH_L if attacking_right else 0.0
        dist = _dist((x, y), (gx, GOAL_Y))
        ang = shot_angle(x, y, attacking_right)
        header = self.through_flag and self.rng.random() < 0.45 and dist < 14
        _, press = self.nearest_opponent((x, y), side)
        pressured = press < 2.0
        p_goal = true_goal_prob(dist, ang, header, pressured, p.finishing - self.fatigue(), self.through_flag)
        speed = (_clamp(self.rng.gauss(58, 9), 35, 80) if header else _clamp(self.rng.gauss(95, 14), 55, 132))
        blockers = sum(1 for q in self.squad(self.opp(side)) if _dist(self.pos[q.id], (x, y)) < dist and
                       abs((self.pos[q.id][1] - y) - (GOAL_Y - y) * ((self.pos[q.id][0] - x) / ((gx - x) or 1e-6))) < 1.2
                       and q.position != "GK")
        r = self.rng.random()
        target_y = GOAL_Y + self.rng.gauss(0, 2.4)
        q = {"distance_m": round(dist, 1), "body_part": "head" if header else "foot", "shot_speed_kmh": round(speed, 1),
             "under_pressure": pressured, "assisted_by": "through_or_cross" if self.through_flag else "none",
             "blockers_in_lane": blockers, "end_y": round(target_y, 2)}
        self.through_flag = False
        gk = f"{self.opp(side)[0]}1"
        if blockers and self.rng.random() < 0.18 * blockers:
            blk = min(self.squad(self.opp(side)), key=lambda qq: _dist(self.pos[qq.id], (x, y))).id
            yield self.emit("shot", 0.6, team=side, player_id=p.id, x=round(x, 2), y=round(y, 2),
                            end_x=round(self.pos[blk][0], 2), end_y=round(self.pos[blk][1], 2), outcome="blocked", qualifiers=q)
            if self.rng.random() < 0.4:
                yield from self.corner(side)
            else:
                self.give_ball(self.opp(side), self.pos[blk][0], self.pos[blk][1], prefer=blk)
                self.reshape()
            return
        if r < p_goal:
            yield self.emit("shot", 0.0, team=side, player_id=p.id, x=round(x, 2), y=round(y, 2), end_x=gx,
                            end_y=round(_clamp(target_y, GOAL_Y - 3.5, GOAL_Y + 3.5), 2), outcome="goal", qualifiers=q)
            self.score[side] += 1
            self.form[side] += 0.4
            self.form[self.opp(side)] -= 0.2
            yield self.emit("goal", self.rng.uniform(55, 80), team=side, player_id=p.id, x=round(x, 2), y=round(y, 2),
                            qualifiers={"score_home": self.score["home"], "score_away": self.score["away"]})
            yield from self.kickoff(self.opp(side))
            return
        on_target = self.rng.random() < 0.52
        if on_target:
            yield self.emit("shot", 0.0, team=side, player_id=p.id, x=round(x, 2), y=round(y, 2), end_x=gx,
                            end_y=round(_clamp(target_y, GOAL_Y - 3.5, GOAL_Y + 3.5), 2), outcome="saved", qualifiers=q)
            yield self.emit("save", 1.5, team=self.opp(side), player_id=gk, x=round(self.pos[gk][0], 2), y=round(self.pos[gk][1], 2),
                            target_id=p.id, qualifiers={"shot_speed_kmh": round(speed, 1)})
            if self.rng.random() < 0.33:
                yield from self.corner(side)
            else:
                self.give_ball(self.opp(side), self.pos[gk][0], self.pos[gk][1], prefer=gk)
                self.reshape()
            return
        wide = target_y + (self.rng.choice([-1, 1]) * self.rng.uniform(4, 10))
        yield self.emit("shot", 0.0, team=side, player_id=p.id, x=round(x, 2), y=round(y, 2), end_x=gx,
                        end_y=round(wide, 2), outcome="off_target", qualifiers=q)
        self.give_ball(self.opp(side), 6 if side == "away" else PITCH_L - 6, GOAL_Y, prefer=gk)
        self.t += self.rng.uniform(15, 25)
        self.reshape()

    def corner(self, side: str) -> Iterator[Event]:
        cx = PITCH_L - 0.5 if side == "home" else 0.5
        cy = 0.5 if self.rng.random() < 0.5 else PITCH_W - 0.5
        taker = f"{side[0]}{self.rng.choice([7, 11, 10])}"
        self.give_ball(side, cx, cy, prefer=taker)
        self.reshape()
        yield self.emit("corner", self.rng.uniform(20, 32), team=side, player_id=taker, x=round(cx, 2), y=round(cy, 2))
        self.through_flag = True

    # ------------------------------------------------------------------ main loop
    def run(self) -> Iterator[Event]:
        yield from self.kickoff("home")
        added = {1: self.rng.randint(1, 3) * 60, 2: self.rng.randint(3, 6) * 60}
        half_end = {1: 45 * 60 + added[1], 2: 90 * 60 + added[2]}
        while True:
            if self.t >= half_end[self.period]:
                if self.period == 1:
                    yield self.emit("half_time", 0.0, qualifiers={"score_home": self.score["home"], "score_away": self.score["away"]})
                    self.period = 2
                    self.t = 45 * 60
                    yield from self.kickoff("away")
                    continue
                yield self.emit("full_time", 0.0, qualifiers={"score_home": self.score["home"], "score_away": self.score["away"]})
                return
            # slow form drift -> momentum
            for s in ("home", "away"):
                self.form[s] = _clamp(self.form[s] * 0.995 + self.rng.gauss(0, 0.03), -1, 1)
            a = self.choose_action()
            if a == "pass":
                yield from self.do_pass()
            elif a == "carry":
                yield from self.do_carry()
            elif a == "dribble":
                yield from self.do_carry(dribble=True)
            else:
                yield from self.do_shot()


def simulate(seed: int = 7) -> tuple[MatchMeta, list[Event]]:
    sim = MatchSimulator(seed)
    events = list(sim.run())
    return sim.meta, events


if __name__ == "__main__":  # pragma: no cover
    import collections
    import sys

    meta, evs = simulate(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
    c = collections.Counter(e.type for e in evs)
    print(meta.home.name, "v", meta.away.name, "events:", len(evs))
    print(dict(c))
    print("final:", evs[-1].qualifiers)
