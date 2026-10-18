"""Producer - the editorial graphics director.

Turns verified insights into vendor-neutral, timed overlay cues
(schema `touchline.overlay/1`, see docs/OVERLAY_CONTRACT.md) keyed to the match clock,
so any rendering partner can play them in sync with the feed.

It is an editor, not a pipe. Moments compete for a small number of on-screen slots, and
for every one the Producer decides, and says why:

* **air**    - the slot is free and the moment is worth it
* **bump**   - it beats what is on air by a clear margin, so the current graphic is cut
* **queue**  - the slot frees up soon and the moment will still be fresh then
* **drop**   - it would repeat what viewers just saw, or it is not worth the wait

The score blends news value (salience), story value (a storyline callback), freshness
(the same kind or player aired recently), and balance (one team hogging the graphics).
Slot occupancy runs on the wall clock, because that is the time viewers actually see.

Human-in-the-loop: in `review` mode non-critical cues wait for approval
(goals and red cards always air); unapproved cues expire.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable, Optional

TEMPLATES = {
    "goal": ("full_banner", 9.0), "chance_saved": ("shot_card", 7.0), "chance_missed": ("shot_card", 7.0),
    "chance_blocked": ("shot_card", 6.0), "line_break": ("pass_card", 6.0), "hard_pass": ("pass_card", 6.0),
    "sprint": ("player_tag", 4.0), "long_carry": ("player_tag", 4.0), "momentum": ("momentum_bar", 8.0),
    "phase": ("phase_meter", 8.0), "press": ("press_card", 7.0), "card_yellow": ("card", 5.0), "card_red": ("card", 8.0),
    "wp_swing": ("wp_chart", 7.0), "brace": ("player_card", 7.0), "hat_trick": ("player_card", 9.0),
    "saves": ("player_card", 6.0), "record_shot": ("shot_card", 6.0), "rhythm": ("rhythm_meter", 6.0),
    "standout": ("player_card", 8.0), "half_time": ("summary", 15.0), "full_time": ("summary", 20.0),
    "story_duel": ("story_card", 8.0), "story_channel": ("story_card", 8.0), "story_keeper": ("story_card", 8.0),
    "story_waste": ("story_card", 7.0), "story_fatigue": ("story_card", 8.0),
}
LAYER = {
    "full_banner": "lower_third", "shot_card": "lower_third", "pass_card": "lower_third", "player_tag": "player_tag",
    "momentum_bar": "side_panel", "phase_meter": "side_panel", "press_card": "side_panel", "card": "lower_third",
    "wp_chart": "side_panel", "player_card": "side_panel", "rhythm_meter": "side_panel", "summary": "full_screen", "story_card": "side_panel",
}
ALWAYS_AIR = {"goal", "card_red", "half_time", "full_time", "hat_trick"}
HOLD_S = (4.5, 9.0)        # how long a graphic stays up, in real seconds
BUMP_MARGIN = 0.18         # a challenger must beat the on-air score by this much to cut it
MAX_WAIT_S = 3.0           # longest a queued graphic may wait for its slot
QUEUE_MIN = 0.45           # below this, a busy slot means drop rather than queue
KIND_FAMILY = {"chance_saved": "chance", "chance_missed": "chance", "chance_blocked": "chance",
               "line_break": "pass", "hard_pass": "pass", "momentum": "flow", "phase": "flow", "wp_swing": "flow"}


class Producer:
    name = "Producer"
    role = "Schedules timed, machine-readable overlay cues with human approval"

    def __init__(self, match_id: str, mode: str = "auto", review_timeout_s: float = 25.0,
                 clock: Callable[[], float] = time.monotonic):
        self.match_id = match_id
        self.mode = mode
        self.review_timeout_s = review_timeout_s
        self.clock = clock
        self.busy: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.queue: dict[str, list[dict]] = {}
        self.history: deque = deque(maxlen=60)    # what aired: (match_t, kind family, team, player)
        self.rundown: deque = deque(maxlen=80)    # every editorial decision, newest last
        self.updates: list[dict] = []             # cue changes for the runtime to publish
        self.n = 0
        self.aired = 0
        self.dropped = 0
        self.counts = {"air": 0, "bump": 0, "queue": 0, "drop": 0}

    def make_cue(self, ins: dict) -> dict:
        self.n += 1
        template, dur = TEMPLATES.get(ins["kind"], ("lower_third_text", 6.0))
        layer = LAYER.get(template, "lower_third")
        viz = ins.get("viz", {})
        anchor = None
        if "x" in viz and viz.get("x") is not None:
            anchor = {"x": viz.get("end_x") or viz["x"], "y": viz.get("end_y") or viz["y"], "units": "pitch_m"}
        studio = ins.get("renders", {}).get("studio", {})
        return {
            "schema": "touchline.overlay/1",
            "cue_id": f"{ins['id']}-C{self.n}",
            "insight_id": ins["id"], "match_id": self.match_id, "kind": ins["kind"],
            "clock": {"match_t": round(ins["t"], 2), "minute": ins["minute"]},
            "in_at_t": round(ins["t"] + 0.5, 2), "duration_s": dur, "out_at_t": round(ins["t"] + 0.5 + dur, 2),
            "layer": layer, "template": template, "priority": int(ins["salience"] * 100),
            "anchor": anchor, "data": viz,
            "copy": {lang: {"title": r["title"], "line": r["lines"][0]["text"] if r["lines"] else ""}
                     for lang, r in studio.items()},
            "evidence": ins["event_ids"], "verification": ins.get("verification", {}).get("status"),
            "approval": "auto",
        }

    # ------------------------------------------------------------------ editorial judgement
    def score(self, ins: dict, now_t: float) -> tuple[float, dict]:
        """How much this moment deserves the screen right now, and why."""
        kind = ins["kind"]
        fam = KIND_FAMILY.get(kind, kind)
        if kind in ALWAYS_AIR:
            return 2.0, {"news": 2.0, "story": 0.0, "fresh": 0.0, "player": 0.0, "balance": 0.0}
        news = float(ins.get("salience", 0.5))
        if kind in ("card_yellow", "brace", "standout"):
            news = max(news, 0.8)  # editorially, cards and milestones are always worth showing
        story = 0.15 if ins.get("storyline") else 0.0
        recent = [h for h in self.history if now_t - h[0] < 300]
        same = sum(1 for h in recent if h[1] == fam)
        player = ins.get("player_id")
        same_player = sum(1 for h in recent if player and h[3] == player and now_t - h[0] < 180)
        fresh = -min(0.4, 0.15 * same)
        player_pen = -0.1 if same_player else 0.0
        team = ins.get("team")
        window = [h for h in self.history if now_t - h[0] < 600 and h[2]]
        balance = 0.0
        if team and len(window) >= 4:
            share = sum(1 for h in window if h[2] == team) / len(window)
            balance = -0.08 if share > 0.7 else 0.05 if share < 0.3 else 0.0
        f = {"news": round(news, 2), "story": story, "fresh": round(fresh, 2), "player": player_pen, "balance": balance}
        return round(news + story + fresh + player_pen + balance, 3), f

    def _reason(self, action: str, f: dict, cue: dict, other: Optional[dict]) -> str:
        why = []
        if f["news"] >= 2:
            why.append("a must-air moment")
        else:
            if f["news"] >= 0.7:
                why.append("high news value")
            if f["story"]:
                why.append("it pays off a storyline")
            if f["fresh"] < 0:
                why.append("viewers saw something similar recently")
            if f.get("player"):
                why.append("the same player featured moments ago")
            if f["balance"] > 0:
                why.append("the other team has had most of the graphics")
            if f["balance"] < 0:
                why.append("this team has had most of the graphics")
        base = ", ".join(why) or "a routine moment"
        o = f" over {other['kind'].replace('_', ' ')} ({other['score']:.2f})" if other else ""
        return {"air": f"Aired: {base}.",
                "bump": f"Cut in{o}: {base}.",
                "queue": f"Queued behind {other['kind'].replace('_', ' ')} ({other['score']:.2f}): {base}." if other else f"Queued: {base}.",
                "drop": f"Dropped{(' for ' + other['kind'].replace('_', ' ') + ' on air') if other else ''}: {base}."}[action]

    def _decide(self, cue: dict, action: str, f: dict, other: Optional[dict]) -> None:
        cue["decision"] = {"action": action, "score": cue["score"], "factors": f,
                           "versus": other["cue_id"] if other else None, "reason": self._reason(action, f, cue, other)}
        self.counts[action] += 1
        self.rundown.append({"cue_id": cue["cue_id"], "insight_id": cue["insight_id"], "kind": cue["kind"],
                             "minute": cue["clock"]["minute"], "layer": cue["layer"], **cue["decision"]})

    def schedule(self, ins: dict, now_t: float) -> Optional[dict]:
        if ins.get("verification", {}).get("status") != "verified":
            self.dropped += 1
            return None
        cue = self.make_cue(ins)
        score, f = self.score(ins, now_t)
        cue["score"] = score
        cue["_ins"] = (now_t, KIND_FAMILY.get(ins["kind"], ins["kind"]), ins.get("team"), ins.get("player_id"))
        layer, wall = cue["layer"], self.clock()
        cur = self.busy.get(layer)
        busy = cur is not None and cur["_until"] > wall and layer != "full_screen"
        if self.mode == "review" and ins["kind"] not in ALWAYS_AIR:
            cue["approval"] = "pending"
            cue["pending_since"] = time.time()
            self.pending[cue["cue_id"]] = cue
            self._decide(cue, "queue", f, None)
            cue["decision"]["reason"] = "Waiting for the producer's approval."
            return self._public(cue)
        if busy and score < cur["score"] + BUMP_MARGIN:
            waiting = self.queue.get(layer) or []
            soon = cur["_until"] - wall <= MAX_WAIT_S
            outranks = score > cur["score"]
            if score >= QUEUE_MIN and (soon or outranks) and (not waiting or score > waiting[0]["score"]):
                for old in waiting:  # a better moment takes the waiting spot
                    old["approval"] = "skipped"
                    old["decision"] = {**old["decision"], "action": "drop", "reason": f"Dropped: {cue['kind'].replace('_', ' ')} took its place in the queue."}
                    self.counts["drop"] += 1
                    self.dropped += 1
                    self.updates.append(self._public(old))
                cue["approval"] = "queued"
                cue["_queued_at"] = wall
                self.queue[layer] = [cue]
                self._decide(cue, "queue", f, cur)
            else:
                cue["approval"] = "skipped"
                cue["preempted_by"] = cur["cue_id"]
                self.dropped += 1
                self._decide(cue, "drop", f, cur)
            return self._public(cue)
        if busy:
            cur["approval"] = "bumped"
            cur["_until"] = wall
            self.updates.append(self._public(dict(cur)))
            self._decide(cue, "bump", f, cur)
        else:
            self._decide(cue, "air", f, None)
        self._air(cue)
        return self._public(cue)

    def tick(self) -> list[dict]:
        """Air queued graphics whose slot has freed; drop the ones that went stale."""
        wall, out = self.clock(), []
        for layer, q in list(self.queue.items()):
            cur = self.busy.get(layer)
            while q:
                cue = q[0]
                if wall - cue["_queued_at"] > HOLD_S[1] + 1.0:
                    q.pop(0)
                    cue["approval"] = "expired"
                    cue["decision"] = {**cue["decision"], "action": "drop", "reason": "Dropped: went stale while waiting for the slot."}
                    self.counts["drop"] += 1
                    self.dropped += 1
                    out.append(self._public(cue))
                    continue
                if cur and cur["_until"] > wall:
                    break
                q.pop(0)
                cue["approval"] = "auto"
                cue["decision"] = {**cue["decision"], "action": "air", "reason": cue["decision"]["reason"].replace("Queued behind", "Aired after")}
                self._air(cue)
                out.append(self._public(cue))
                break
        out += self.updates
        self.updates = []
        return out

    @staticmethod
    def _public(cue: dict) -> dict:
        return {k: v for k, v in cue.items() if not k.startswith("_")}

    def _air(self, cue: dict) -> None:
        hold = min(HOLD_S[1], max(HOLD_S[0], cue["duration_s"]))
        cue["_until"] = self.clock() + hold
        self.busy[cue["layer"]] = cue
        self.history.append(cue["_ins"])
        self.aired += 1

    def decide(self, cue_id: str, approve: bool, now_t: float) -> Optional[dict]:
        cue = self.pending.pop(cue_id, None)
        if not cue:
            return None
        cue["approval"] = "approved" if approve else "rejected"
        if approve:
            # re-time the cue to air now on the match clock
            cue["in_at_t"] = round(now_t + 0.5, 2)
            cue["out_at_t"] = round(now_t + 0.5 + cue["duration_s"], 2)
            cue["decision"] = {**cue.get("decision", {}), "action": "air", "reason": "Aired: approved by the producer."}
            self._air(cue)
        else:
            cue["decision"] = {**cue.get("decision", {}), "action": "drop", "reason": "Dropped by the producer."}
            self.dropped += 1
        return self._public(cue)

    def expire(self) -> list[dict]:
        out = []
        for cid, cue in list(self.pending.items()):
            if time.time() - cue["pending_since"] > self.review_timeout_s:
                cue["approval"] = "expired"
                self.pending.pop(cid)
                self.dropped += 1
                out.append(self._public(cue))
        return out

    def stats(self) -> dict:
        return {"mode": self.mode, "cues": self.n, "aired": self.aired, "dropped_or_expired": self.dropped,
                "pending": len(self.pending), "decisions": dict(self.counts),
                "queued": sum(len(q) for q in self.queue.values())}
