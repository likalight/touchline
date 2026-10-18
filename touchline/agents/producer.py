"""Producer - the graphics director.

Turns verified insights into vendor-neutral, timed overlay cues
(schema `touchline.overlay/1`, see docs/OVERLAY_CONTRACT.md) keyed to the match clock,
so any rendering partner can play them in sync with the feed.

* one cue per layer at a time; higher-priority cues pre-empt lower ones
* human-in-the-loop: in `review` mode non-critical cues wait in a producer queue for
  approval (goals and red cards always auto-air); unapproved cues expire
"""
from __future__ import annotations

import time
from typing import Optional

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


class Producer:
    name = "Producer"
    role = "Schedules timed, machine-readable overlay cues with human approval"

    def __init__(self, match_id: str, mode: str = "auto", review_timeout_s: float = 25.0):
        self.match_id = match_id
        self.mode = mode
        self.review_timeout_s = review_timeout_s
        self.busy: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.n = 0
        self.aired = 0
        self.dropped = 0

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

    def schedule(self, ins: dict, now_t: float) -> Optional[dict]:
        if ins.get("verification", {}).get("status") != "verified":
            self.dropped += 1
            return None
        cue = self.make_cue(ins)
        layer = cue["layer"]
        cur = self.busy.get(layer)
        if cur and cur["out_at_t"] > now_t and cur["priority"] > cue["priority"] and layer != "full_screen":
            cue["preempted_by"] = cur["cue_id"]
            cue["approval"] = "skipped"
            self.dropped += 1
            return cue
        if self.mode == "review" and ins["kind"] not in ALWAYS_AIR:
            cue["approval"] = "pending"
            cue["pending_since"] = time.time()
            self.pending[cue["cue_id"]] = cue
            return cue
        self._air(cue)
        return cue

    def _air(self, cue: dict) -> None:
        self.busy[cue["layer"]] = cue
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
            self._air(cue)
        else:
            self.dropped += 1
        return cue

    def expire(self) -> list[dict]:
        out = []
        for cid, cue in list(self.pending.items()):
            if time.time() - cue["pending_since"] > self.review_timeout_s:
                cue["approval"] = "expired"
                self.pending.pop(cid)
                self.dropped += 1
                out.append(cue)
        return out

    def stats(self) -> dict:
        return {"mode": self.mode, "cues": self.n, "aired": self.aired, "dropped_or_expired": self.dropped,
                "pending": len(self.pending)}
