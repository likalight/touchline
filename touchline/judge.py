"""A visitor-owned 90-second replay through the real, chronological agent pipeline."""
from __future__ import annotations

import asyncio
import secrets

from touchline.runtime import MatchSession


class JudgeSession(MatchSession):
    def __init__(self):
        super().__init__(seed=221, speed=1)
        self.broadcast_outputs = False
        self.control_token = secrets.token_urlsafe(32)
        self.paused = True
        self._quiet = True
        self.chapter = None
        goals = [e for e in self.events if e.type == "goal"]
        selected = [next(e for e in goals if e.team == "away"), goals[-2], goals[-1]]
        titles = ["The mistake", "The redemption", "The winner"]
        self.chapters = [{"title": title, "event_id": event.id, "start": event.t - 5, "end": event.t + 25}
                         for title, event in zip(titles, selected)]

    def publish(self, msg):
        if not self._quiet:
            super().publish(msg)

    def describe(self):
        return {**super().describe(), "judge": {"duration_s": 90, "chapter": self.chapter,
                                               "chapters": [c["title"] for c in self.chapters]}}

    def replay_history(self):
        return [i for i in self.insights if i["kind"] in {"goal", "hat_trick"}
                and any(c["start"] <= i["t"] <= c["end"] for c in self.chapters)]

    async def _wait(self, seconds):
        while self.paused:
            await asyncio.sleep(0.1)
        while seconds > 0:
            step = min(0.1, seconds)
            await asyncio.sleep(step)
            if not self.paused:
                seconds -= step

    async def _run(self):
        await self._wait(0)
        index = 0
        for number, chapter in enumerate(self.chapters):
            self._quiet = True
            # Every preceding event is interpreted; no pre-written callbacks or future state.
            while index < len(self.events) and self.events[index].t < chapter["start"]:
                for event in self.guard.push(self.events[index].model_dump()):
                    await self._play(event, realtime=True)
                index += 1
                await asyncio.sleep(0)
            # Skipped history must not occupy the screen when a new excerpt begins.
            self.producer.busy.clear()
            self.producer.queue.clear()
            self.producer.pending.clear()
            self.producer.updates.clear()
            self._quiet = False
            self.chapter = number
            self.publish({"type": "judge_chapter", "index": number, "title": chapter["title"],
                          "event_id": chapter["event_id"]})
            self.publish({"type": "state", **self.snapshot()})
            clock = chapter["start"]
            while index < len(self.events) and self.events[index].t <= chapter["end"]:
                event = self.events[index]
                await self._wait(max(0, event.t - clock))
                for accepted in self.guard.push(event.model_dump()):
                    await self._play(accepted, realtime=True)
                clock = event.t
                index += 1
            await self._wait(max(0, chapter["end"] - clock))
        await asyncio.gather(*list(self.pending_tasks), return_exceptions=True)
        self.done = True
        self.paused = True
        self.publish({"type": "state", **self.snapshot()})
        self.publish({"type": "done"})
