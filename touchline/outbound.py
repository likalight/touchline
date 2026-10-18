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

    @property
    def enabled(self) -> bool:
        return os.getenv("TOUCHLINE_OUTBOUND", "on") != "off" and bool(
            os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE") or os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"))

    def status(self) -> dict:
        return {"enabled": self.enabled, "hub": HUB, "sent": self.sent, "dropped": self.dropped, "errors": self.errors}

    def emit(self, msg: dict) -> None:
        if not self.enabled:
            return
        if self.q is None:
            self.q = asyncio.Queue(maxsize=2000)
            self.task = asyncio.get_event_loop().create_task(self._run())
        try:
            self.q.put_nowait(msg)
        except asyncio.QueueFull:
            self.dropped += 1

    async def _run(self) -> None:  # pragma: no cover - needs Azure
        from azure.eventhub import EventData
        from azure.eventhub.aio import EventHubProducerClient

        if os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"):
            prod = EventHubProducerClient.from_connection_string(os.environ["TOUCHLINE_EVENTHUB_CONNECTION"], eventhub_name=HUB)
        else:
            from azure.identity.aio import DefaultAzureCredential

            prod = EventHubProducerClient(os.environ["TOUCHLINE_EVENTHUB_NAMESPACE"], HUB, DefaultAzureCredential())
        async with prod:
            while True:
                first = await self.q.get()
                batch = [first]
                while not self.q.empty() and len(batch) < 50:
                    batch.append(self.q.get_nowait())
                try:
                    await prod.send_batch([EventData(json.dumps(m, ensure_ascii=False)) for m in batch],
                                          partition_key=batch[0].get("match_id"))
                    self.sent += len(batch)
                except Exception as exc:
                    self.errors += 1
                    log.warning("outbound publish failed: %s", exc)
                    await asyncio.sleep(2)


def insight_message(session_id: str, match_id: str, ins: dict) -> dict:
    studio = (ins.get("renders") or {}).get("studio") or {}
    return {"type": "insight", "session": session_id, "match_id": match_id, "id": ins["id"], "kind": ins["kind"],
            "minute": ins["minute"], "team": ins.get("team"), "salience": ins.get("salience"),
            "verification": (ins.get("verification") or {}).get("status"),
            "decision": ((ins.get("cue") or {}).get("decision") or {}).get("action"),
            "copy": {lang: {"title": r["title"], "line": r["lines"][0]["text"] if r.get("lines") else ""} for lang, r in studio.items()},
            "evidence": ins.get("event_ids", [])}


outbound = Outbound()
