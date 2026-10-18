"""IngestGuard - the front door. Validates, de-duplicates and re-orders the live feed.

Real feeds arrive late, twice, out of order or malformed. The guard:
* validates each payload against the `Event` contract (pydantic) and quarantines failures
* drops exact duplicate event IDs
* holds a small re-order buffer keyed on `seq` and releases events in order, or after a
  short timeout so a single lost event never stalls the show
`FaultInjector` reproduces those failures on demand (`?chaos=0.05`) to prove recovery.
"""
from __future__ import annotations

import heapq
import random
import time
from typing import Iterable, Iterator

from pydantic import ValidationError

from touchline.schema import Event


class FaultInjector:
    def __init__(self, rate: float = 0.0, seed: int = 0):
        self.rate = rate
        self.rng = random.Random(seed)
        self.injected = {"duplicate": 0, "reorder": 0, "corrupt": 0}

    def apply(self, events: Iterable[Event]) -> Iterator[dict]:
        held = None
        for ev in events:
            d = ev.model_dump()
            r = self.rng.random()
            if self.rate and ev.type not in ("kickoff", "half_time", "full_time", "goal"):
                if r < self.rate / 3:
                    self.injected["corrupt"] += 1
                    bad = dict(d)
                    bad["type"] = "teleport"
                    bad["id"] = d["id"] + "x"
                    yield bad
                elif r < 2 * self.rate / 3:
                    self.injected["duplicate"] += 1
                    yield d
                    yield dict(d)
                    continue
                elif r < self.rate and held is None:
                    self.injected["reorder"] += 1
                    held = d
                    continue
            yield d
            if held is not None:
                yield held
                held = None
        if held is not None:
            yield held


class IngestGuard:
    name = "IngestGuard"
    role = "Validates, de-duplicates and re-orders the incoming event feed"

    def __init__(self, max_wait_s: float = 1.5):
        self.seen: set[str] = set()
        self.buffer: list[tuple[int, float, Event]] = []
        self.next_seq = 1
        self.max_wait_s = max_wait_s
        self.stats = {"accepted": 0, "duplicates": 0, "quarantined": 0, "reordered": 0, "gaps_skipped": 0}
        self.quarantine: list[dict] = []

    def push(self, payload: dict) -> list[Event]:
        try:
            ev = Event.model_validate(payload)
        except ValidationError as exc:
            self.stats["quarantined"] += 1
            self.quarantine.append({"id": payload.get("id"), "error": str(exc.errors()[0]["msg"])})
            self.quarantine = self.quarantine[-50:]
            return self.release()
        if ev.id in self.seen:
            self.stats["duplicates"] += 1
            return self.release()
        self.seen.add(ev.id)
        if ev.seq != self.next_seq:
            self.stats["reordered"] += 1 if ev.seq > self.next_seq else 0
        heapq.heappush(self.buffer, (ev.seq, time.monotonic(), ev))
        return self.release()

    def release(self, force: bool = False) -> list[Event]:
        out = []
        while self.buffer:
            seq, arrived, ev = self.buffer[0]
            if seq <= self.next_seq or force or time.monotonic() - arrived > self.max_wait_s:
                heapq.heappop(self.buffer)
                if seq > self.next_seq:
                    self.stats["gaps_skipped"] += 1
                self.next_seq = max(self.next_seq, seq + 1)
                self.stats["accepted"] += 1
                out.append(ev)
            else:
                break
        return out

    def flush(self) -> list[Event]:
        return self.release(force=True)
