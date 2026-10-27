"""StorylineKeeper - long-term match memory, so commentary has callbacks, not just moments.

Broadcasters don't describe events in isolation; they tell stories that run across the
90 minutes. The StorylineKeeper watches every event and maintains *threads*:

  duel        an attacker keeps beating the same defender
  channel     a team keeps getting into the final third down the same side
  keeper      a goalkeeper is saving more than the chances say he should
  waste       a forward with lots of xG and no goal
  fatigue     a team's passing falls away late in the game
  error       a player's loss of possession led to a goal (and, later, redemption)
  comeback    a team that was nearly beaten fights back

It does three things with them:
  1. `observe`   updates threads and returns *story moments* when a thread matures
  2. `callbacks` attaches callback lines to any live insight ("it began with a loss of
                 possession by X, 9 seconds earlier"; "redemption for X")
  3. `recount`   independently re-derives a story frame's numbers from the raw events;
                 the FactChecker calls it, so story claims are verified like every other claim
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from touchline.agents.scout import Moment
from touchline.analytics.models import fx, fy
from touchline.analytics.state import Enriched, MatchState
from touchline.schema import PITCH_L

ALL = ["casual", "analyst", "studio", "access"]


def F(k: str, ev: list[str] | None = None, aud: list[str] | None = None, **p) -> dict:
    return {"k": k, "p": p, "ev": ev or [], "aud": aud or ALL}


def lane(y: float, side: str) -> str:
    ay = fy(y, side)
    return "left" if ay > 45.3 else "right" if ay < 22.7 else "centre"


class StorylineKeeper:
    name = "StorylineKeeper"
    role = "Keeps match-long narrative threads and writes callbacks"

    def __init__(self, state: MatchState):
        self.s = state
        self.duels: dict[tuple[str, str], list[str]] = defaultdict(list)  # (attacker, defender) -> event ids
        self.entries: dict[str, list[tuple[float, str, str]]] = {"home": [], "away": []}  # (t, lane, event id)
        self.keeper: dict[str, dict] = defaultdict(lambda: {"xg_on_target": 0.0, "conceded": 0, "saves": 0, "events": []})
        self.errors: dict[str, dict] = {}  # culprit pid -> {minute, goal_event, loss_event}
        self.low_wp: dict[str, tuple[float, int, str]] = {"home": (1.0, 0, ""), "away": (1.0, 0, "")}
        self.fired: set[str] = set()
        self.last_story_t = -999.0
        self.threads: list[dict] = []  # matured threads, for recaps
        self.arcs: list[dict] = []  # callbacks that aired, for recaps
        self.redeemed: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def tname(self, side: str) -> str:
        return (self.s.meta.home if side == "home" else self.s.meta.away).name

    def opp(self, side: str) -> str:
        return "away" if side == "home" else "home"

    def _nearest_opponent(self, ev) -> Optional[str]:
        if not ev.frame or ev.x is None:
            return None
        pre = "a" if ev.team == "home" else "h"
        best, bd = None, 3.2
        for pid, (x, y) in ev.frame.items():
            if pid[0] == pre and not pid.endswith("1"):
                d = ((x - ev.x) ** 2 + (y - ev.y) ** 2) ** 0.5
                if d < bd:
                    best, bd = pid, d
        return best

    def _recent(self, before_t: float, window: float):
        for eid in reversed(list(self.s.events.keys())[-60:]):
            e = self.s.events[eid]
            if e.t < before_t - window:
                break
            yield e

    # ------------------------------------------------------------------ observe
    def observe(self, en: Enriched) -> list[Moment]:
        e = en.ev
        s = self.s
        out: list[Moment] = []
        side = e.team
        # comeback memory: lowest win probability per team, and when
        if en.wp_after:
            for t in ("home", "away"):
                if en.wp_after[t] < self.low_wp[t][0] and e.minute > 10:
                    self.low_wp[t] = (en.wp_after[t], e.minute, e.id)
        # duels: an attacker beats a defender with the ball, or a defender wins it back from him
        if e.type == "dribble" and e.outcome == "success":
            d = self._nearest_opponent(e)
            if d:
                key = (e.player_id, d)
                self.duels[key].append(e.id)
                n = len(self.duels[key])
                tag = f"duel:{key}:{n}"
                duel_stories = sum(1 for th in self.threads if th["kind"] == "story_duel")
                if n in (4, 6) and tag not in self.fired and duel_stories < 3:
                    self.fired.add(tag)
                    out.append(self._story("story_duel", e, side, {"attacker": e.player_id, "defender": d, "count": n,
                                                                  "events": list(self.duels[key])}))
        # channel: entries into the final third, by lane
        if e.type in ("pass", "carry", "dribble") and e.outcome in ("complete", "success") and e.end_x is not None:
            if fx(e.x, side) < 70 <= fx(e.end_x, side):
                self.entries[side].append((e.t, lane(e.end_y, side), e.id))
                recent = [r for r in self.entries[side] if r[0] >= e.t - 900]
                if len(recent) >= 8:
                    counts = defaultdict(list)
                    for r in recent:
                        counts[r[1]].append(r[2])
                    ln, ids = max(counts.items(), key=lambda kv: len(kv[1]))
                    tag = f"channel:{side}:{ln}:{int(e.t // 1200)}"
                    if ln != "centre" and len(ids) / len(recent) >= 0.55 and tag not in self.fired:
                        self.fired.add(tag)
                        out.append(self._story("story_channel", e, side, {"lane": ln, "count": len(ids), "total": len(recent),
                                                                         "events": ids[-6:]}))
        # keepers
        if e.type == "shot" and e.outcome in ("goal", "saved") and en.xg is not None:
            gk = e.qualifiers.get("goalkeeper_id", f"{self.opp(side)[0]}1")
            k = self.keeper[gk]
            k["xg_on_target"] += en.xg
            k["events"].append(e.id)
            if e.outcome == "goal":
                k["conceded"] += 1
            else:
                k["saves"] += 1
                prevented = k["xg_on_target"] - k["conceded"]
                for level in (0.7, 1.4):
                    tag = f"keeper:{gk}:{level}"
                    if prevented >= level and k["saves"] >= 3 and tag not in self.fired:
                        self.fired.add(tag)
                        out.append(self._story("story_keeper", e, self.opp(side), {"keeper": gk, "xg": round(k["xg_on_target"], 2),
                                                                                  "conceded": k["conceded"], "saves": k["saves"],
                                                                                  "events": k["events"][-6:]}))
        # wasteful finishing
        if e.type == "shot" and e.outcome != "goal":
            p = s.pl[e.player_id]
            tag = f"waste:{e.player_id}"
            if p["xg"] >= 0.9 and p["goals"] == 0 and tag not in self.fired:
                self.fired.add(tag)
                shots = [x.id for x in s.events.values() if x.type == "shot" and x.player_id == e.player_id]
                out.append(self._story("story_waste", e, side, {"player": e.player_id, "xg": round(p["xg"], 2),
                                                               "shots": int(p["shots"]), "events": shots[-6:]}))
        # costly errors and redemption
        if e.type == "goal":
            shot = next((x for x in self._recent(e.t, 3) if x.type == "shot" and x.team == side), None)
            if shot:
                loss = next((x for x in self._recent(shot.t, 25) if x.team == self.opp(side) and x.player_id and
                             ((x.type == "pass" and x.outcome == "intercepted") or (x.type in ("dribble", "carry") and x.outcome == "lost"))),
                            None)
                if loss and loss.player_id[1:] != "1":
                    self.errors[loss.player_id] = {"minute": e.minute, "goal": e.id, "loss": loss.id}
        # fatigue (once per team, after 72')
        if e.minute >= 72 and e.type == "pass" and side:
            tag = f"fatigue:{side}"
            if tag not in self.fired:
                first = [x for x in s.events.values() if x.type == "pass" and x.team == side and x.period == 1]
                late = [x for x in s.events.values() if x.type == "pass" and x.team == side and x.t >= e.t - 900]
                if len(first) > 100 and len(late) > 40:
                    b = sum(x.outcome == "complete" for x in first) / len(first)
                    a = sum(x.outcome == "complete" for x in late) / len(late)
                    if b - a >= 0.07:
                        self.fired.add(tag)
                        out.append(self._story("story_fatigue", e, side, {"before_pct": round(b * 100), "after_pct": round(a * 100),
                                                                         "events": [e.id]}))
        # pace stories so they don't crowd the live moments
        if out and e.t - self.last_story_t < 150 and e.type != "goal":
            return []
        if out:
            self.last_story_t = e.t
        return out

    def _story(self, kind: str, e, side: str, data: dict) -> Moment:
        th = {"kind": kind, "minute": e.minute, "team": side, **data}
        self.threads.append(th)
        return Moment(kind, 0.58, e.t, e.minute, side, [e.id], data.get("attacker") or data.get("player") or data.get("keeper"),
                      {"thread": th})

    # ------------------------------------------------------------------ frames for story moments
    def frames(self, mo: Moment) -> tuple[dict, list[dict], dict]:
        th = mo.data["thread"]
        n = self.s.name
        k = mo.kind
        ev = th["events"]
        if k == "story_duel":
            head = F("h.story_duel", ev[-1:], attacker=n(th["attacker"]), defender=n(th["defender"]))
            reasons = [F("s.duel", ev, attacker=n(th["attacker"]), defender=n(th["defender"]), count=th["count"])]
            viz = {"type": "story", "kind": "duel", "players": [th["attacker"], th["defender"]], "events": ev}
        elif k == "story_channel":
            head = F("h.story_channel", ev[-1:], team=self.tname(th["team"]), lane=f"@v.lane.{th['lane']}")
            reasons = [F("s.channel", ev, team=self.tname(th["team"]), lane=f"@v.lane.{th['lane']}", count=th["count"], total=th["total"])]
            viz = {"type": "story", "kind": "channel", "lane": th["lane"], "team": th["team"], "events": ev}
        elif k == "story_keeper":
            head = F("h.story_keeper", ev[-1:], keeper=n(th["keeper"]), team=self.tname(th["team"]))
            reasons = [F("s.keeper", ev, keeper=n(th["keeper"]), xg=th["xg"], conceded=th["conceded"], saves=th["saves"])]
            viz = {"type": "story", "kind": "keeper", "players": [th["keeper"]], "events": ev}
        elif k == "story_waste":
            head = F("h.story_waste", ev[-1:], player=n(th["player"]))
            reasons = [F("s.waste", ev, player=n(th["player"]), xg=th["xg"], shots=th["shots"])]
            viz = {"type": "story", "kind": "waste", "players": [th["player"]], "events": ev}
        else:  # story_fatigue
            head = F("h.story_fatigue", ev, team=self.tname(th["team"]))
            reasons = [F("s.fatigue", ev, team=self.tname(th["team"]), before_pct=th["before_pct"], after_pct=th["after_pct"])]
            viz = {"type": "story", "kind": "fatigue", "team": th["team"], "events": ev}
        return head, reasons, viz

    # ------------------------------------------------------------------ callbacks on live insights
    def callbacks(self, ins: dict) -> list[dict]:
        s = self.s
        out: list[dict] = []
        k = ins["kind"]
        if k == "goal":
            goal = s.events[ins["event_ids"][-1]]
            side = goal.team
            # the error that started it
            for culprit, err in self.errors.items():
                if err["goal"] == goal.id:
                    loss = s.events[err["loss"]]
                    out.append(F("s.error", [loss.id, goal.id], culprit=s.name(culprit), seconds=round(goal.t - loss.t)))
            # redemption: this scorer cost a goal earlier (told once)
            err = self.errors.get(goal.player_id)
            if err and err["goal"] != goal.id and goal.player_id not in self.redeemed:
                self.redeemed.add(goal.player_id)
                out.append(F("s.redemption", [err["loss"], goal.id], player=s.name(goal.player_id), minute=err["minute"]))
            # with ten men
            red = next((e for e in s.events.values() if e.type == "card" and e.team == side and e.outcome in ("red", "second_yellow")
                        and e.t < goal.t), None)
            told = sum(1 for x in self.arcs if x["k"] == "s.ten_men")
            if red and told < 2:
                out.insert(0, F("s.ten_men", [red.id, goal.id], team=self.tname(side), minute=red.minute))
            # comeback from a low win probability (only what was known before this goal)
            low, minute, eid = 1.0, 0, ""
            for en in s.enriched.values():
                if en.ev.t >= goal.t:
                    break
                if en.wp_after and en.ev.minute > 10 and en.wp_after[side] < low:
                    low, minute, eid = en.wp_after[side], en.ev.minute, en.ev.id
            sc = goal.qualifiers
            ours, theirs = (sc.get("score_home"), sc.get("score_away")) if side == "home" else (sc.get("score_away"), sc.get("score_home"))
            if eid and low <= 0.25 and ours is not None and ours >= theirs:
                out.append(F("s.comeback", [eid, goal.id], team=self.tname(side), low_pct=round(low * 100), minute=minute))
            # against the run of play
            share = self._threat_share(side, goal.t)
            if share is not None and share < 0.3:
                out.append(F("s.run_of_play", [goal.id], ["analyst", "studio", "casual"], team=self.tname(side), share_pct=round(share * 100)))
        if k in ("goal", "chance_saved", "chance_missed") and len(out) < 2:
            # keeper context on a save / finisher context on a miss
            if k == "chance_saved":
                save = s.events[ins["event_ids"][-1]]
                gk, side = save.player_id, save.team
                shots = [e for e in s.events.values() if e.type == "shot" and e.team != side and e.outcome in ("goal", "saved")
                         and e.qualifiers.get("goalkeeper_id", f"{side[0]}1") == gk
                         and e.t <= save.t]
                saves = sum(e.outcome == "saved" for e in shots)
                if saves >= 3:
                    out.append(F("s.keeper", [e.id for e in shots[-4:]], ["analyst", "studio"], keeper=s.name(gk),
                                 xg=round(sum(s.enriched[e.id].xg for e in shots), 2),
                                 conceded=sum(e.outcome == "goal" for e in shots), saves=saves))
        out = out[:2]
        for f in out:
            self.arcs.append({**f, "minute": ins["minute"], "kind": ins["kind"]})
        return out

    def _threat_share(self, side: str, t: float) -> Optional[float]:
        tot = {"home": 0.0, "away": 0.0}
        for eid in reversed(list(self.s.enriched.keys())[-400:]):
            en = self.s.enriched[eid]
            if en.ev.t < t - 300:
                break
            if en.ev.t >= t - 1 or not en.ev.team:
                continue
            tot[en.ev.team] += max(en.xt_added, 0) + 0.6 * (en.xg or 0)
        allv = tot["home"] + tot["away"]
        return tot[side] / allv if allv > 0.08 else None

    # ------------------------------------------------------------------ independent recount (FactChecker uses this)
    def recount(self, fr: dict) -> Optional[str]:
        """Re-derive a story frame's numbers from raw events. Returns an issue string or None."""
        s = self.s
        k, p = fr["k"], fr["p"]
        pid = {pl.name: pl.id for pl in s.players.values()}
        if k == "s.duel":
            att, de = pid.get(p["attacker"]), pid.get(p["defender"])
            n = sum(1 for e in (s.events[i] for i in fr["ev"]) if e.type == "dribble" and e.outcome == "success" and e.player_id == att)
            if n != p["count"] or not de:
                return f"duel recount {n} != {p['count']}"
        elif k == "s.keeper":
            gk = pid.get(p["keeper"])
            side = s.players[gk].team
            shots = [e for e in s.events.values() if e.type == "shot" and e.team != side and e.outcome in ("goal", "saved")
                     and e.qualifiers.get("goalkeeper_id", f"{side[0]}1") == gk
                     and e.t <= s.events[fr["ev"][-1]].t]
            xg = sum(s.enriched[e.id].xg for e in shots)
            conceded = sum(e.outcome == "goal" for e in shots)
            if abs(xg - p["xg"]) > 0.011 or conceded != p["conceded"]:
                return f"keeper recount xg {xg:.2f}/{conceded} != {p['xg']}/{p['conceded']}"
        elif k == "s.waste":
            pl = pid.get(p["player"])
            last_t = s.events[fr["ev"][-1]].t
            shots = [e for e in s.events.values() if e.type == "shot" and e.player_id == pl and e.t <= last_t]
            xg = sum(s.enriched[e.id].xg for e in shots)
            if abs(xg - p["xg"]) > 0.011 or len(shots) != p["shots"] or any(e.outcome == "goal" for e in shots):
                return "waste recount mismatch"
        elif k == "s.error":
            loss, goal = s.events[fr["ev"][0]], s.events[fr["ev"][-1]]
            if s.name(loss.player_id) != p["culprit"] or round(goal.t - loss.t) != p["seconds"] or loss.team == goal.team:
                return "error recount mismatch"
        elif k in ("s.ten_men", "rc.ten_men"):
            red, goal = s.events[fr["ev"][0]], s.events[fr["ev"][-1]]
            if red.type != "card" or red.team != goal.team or red.minute != p["minute"]:
                return "ten men recount mismatch"
        elif k == "s.channel":
            n = len(fr["ev"]) if fr["ev"] else 0
            if p["count"] < n or p["count"] > p["total"]:
                return "channel recount mismatch"
        return None
