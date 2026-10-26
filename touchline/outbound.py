"""Outbound event stream: every verified insight, and every full time, onto Azure Event Hubs.

Downstream systems subscribe instead of polling: the `packages` Azure Function turns full-time
events into post-match packages and goals into social cards, and a broadcaster's CMS, social
tooling or data warehouse can add their own consumer group. Fire-and-forget from the hot path:
a bounded queue and a background sender, so a slow hub never delays a graphic.

Enabled when TOUCHLINE_EVENTHUB_NAMESPACE (managed identity) or TOUCHLINE_EVENTHUB_CONNECTION is set.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

log = logging.getLogger("touchline.outbound")
HUB = os.getenv("TOUCHLINE_OUTBOUND_HUB", "touchline-insights")


class Outbound:
    def __init__(self) -> None:
        self.q: Optional[asyncio.Queue] = None
        self.task: Optional[asyncio.Task] = None
        self.sent = 0
        self.dropped = 0
        self.errors = 0
        self.retries = 0
        self.inflight = 0

    @property
    def enabled(self) -> bool:
        return os.getenv("TOUCHLINE_OUTBOUND", "on") != "off" and bool(
            os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE") or os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"))

    def status(self) -> dict:
        return {"enabled": self.enabled, "hub": HUB, "sent": self.sent, "dropped": self.dropped, "errors": self.errors,
                "retries": self.retries, "pending": (self.q.qsize() if self.q else 0) + self.inflight,
                "durability": "process memory; retries while running, no durable outbound outbox"}

    def emit(self, msg: dict) -> None:
        if not self.enabled:
            return
        if self.q is None:
            self.q = asyncio.Queue(maxsize=2000)
        if self.task is None or self.task.done():
            self.task = asyncio.get_event_loop().create_task(self._run())
        try:
            self.q.put_nowait(msg)
        except asyncio.QueueFull:
            self.dropped += 1

    async def _send(self, prod, msg):
        from azure.eventhub import EventData
        attempt = 0
        while True:
            try:
                await prod.send_batch([EventData(json.dumps(msg, ensure_ascii=False))],
                                      partition_key=msg.get("match_id"))
                self.sent += 1
                return
            except Exception as exc:
                self.errors += 1
                self.retries += 1
                attempt += 1
                log.warning("outbound publish failed; retaining event for retry: %s", exc)
                await asyncio.sleep(min(10, 2 ** min(attempt, 4)))

    async def close(self, timeout=5):
        if self.task is None:
            return
        try:
            await asyncio.wait_for(self.q.join(), timeout=timeout)
        except asyncio.TimeoutError:
            self.dropped += self.q.qsize() + self.inflight
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.task = self.q = None
        self.inflight = 0

    async def _run(self) -> None:  # pragma: no cover - needs Azure
        from azure.eventhub.aio import EventHubProducerClient

        credential = None
        if os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"):
            prod = EventHubProducerClient.from_connection_string(os.environ["TOUCHLINE_EVENTHUB_CONNECTION"], eventhub_name=HUB)
        else:
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            prod = EventHubProducerClient(os.environ["TOUCHLINE_EVENTHUB_NAMESPACE"], HUB, credential)
        try:
            async with prod:
                while True:
                    msg = await self.q.get()
                    self.inflight = 1
                    await self._send(prod, msg)
                    self.inflight = 0
                    self.q.task_done()
        finally:
            if credential:
                await credential.close()


def insight_message(session_id: str, match_id: str, ins: dict) -> dict:
    studio = (ins.get("renders") or {}).get("studio") or {}
    return {"type": "insight", "session": session_id, "match_id": match_id, "id": ins["id"], "kind": ins["kind"],
            "minute": ins["minute"], "team": ins.get("team"), "salience": ins.get("salience"),
            "verification": (ins.get("verification") or {}).get("status"),
            "decision": ((ins.get("cue") or {}).get("decision") or {}).get("action"),
            "copy": {lang: {"title": r["title"], "line": r["lines"][0]["text"] if r.get("lines") else ""} for lang, r in studio.items()},
            "evidence": ins.get("event_ids", [])}


outbound = Outbound()
