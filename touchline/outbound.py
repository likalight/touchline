"""Outbound event stream: every verified insight, and every full time, onto Azure Event Hubs.

Downstream systems subscribe instead of polling: the `packages` Azure Function turns full-time
events into post-match packages and goals into social cards, and a broadcaster's CMS, social
tooling or data warehouse can add their own consumer group. With TOUCHLINE_OUTBOX_URL,
publish awaits a Blob commit before the background sender delivers the message. Input
journal replay reconstructs any work interrupted before that commit. Without an outbox,
the bounded in-process queue retains the original non-durable development behaviour.

Enabled when TOUCHLINE_EVENTHUB_NAMESPACE (managed identity) or TOUCHLINE_EVENTHUB_CONNECTION is set.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import time
from typing import Optional

log = logging.getLogger("touchline.outbound")
HUB = os.getenv("TOUCHLINE_OUTBOUND_HUB", "touchline-insights")


def delivery_key(msg: dict) -> str:
    """Stable source identity, excluding process/session IDs and wall-clock timestamps.

    Reusing a synthetic match ID intentionally denotes the same source match. A new
    real match must have a new match_id. Changed application copy is not a new event.
    """
    if not msg.get("match_id") or msg.get("type") not in ("insight", "full_time"):
        raise ValueError("Outbox requires a match identity and supported message type")
    if msg["type"] == "insight" and not msg.get("id"):
        raise ValueError("Insight requires a stable insight identity")
    identity = {k: msg.get(k) for k in ("type", "match_id", "id", "kind")}
    identity["evidence"] = sorted(msg.get("evidence", []))
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class DurableOutbox:
    """Single-writer transactional document, using the Blob store's ETag CAS.

    Pending messages survive a restart. Send and acknowledge are separate commits,
    so delivery is at least once: consumers must deduplicate delivery_id. The finite
    ledger fails explicitly at its limit; it never silently forgets acknowledged IDs.
    """
    LIMIT = 10000

    def __init__(self, store, source: dict):
        self.store, self.source = store, source
        self.document = {"schema": "touchline.outbox/1", "source": source, "pending": {}, "acknowledged": []}
        self.lock = asyncio.Lock()

    async def restore(self):
        saved = await self.store.read()
        if saved is not None:
            if (saved.get("schema") != "touchline.outbox/1" or saved.get("source") != self.source
                    or not isinstance(saved.get("pending"), dict) or not isinstance(saved.get("acknowledged"), list)
                    or len(saved["pending"]) + len(saved["acknowledged"]) > self.LIMIT):
                raise ValueError("Invalid outbox or different source; refusing unsafe output replay")
            self.document = copy.deepcopy(saved)

    async def enqueue(self, msg: dict) -> bool:
        key = delivery_key(msg)
        async with self.lock:
            if key in self.document["pending"] or key in self.document["acknowledged"]:
                return False
            if len(self.document["pending"]) + len(self.document["acknowledged"]) >= self.LIMIT:
                raise RuntimeError("Outbox ledger full; archive completed matches before accepting more")
            updated = copy.deepcopy(self.document)
            updated["pending"][key] = {**copy.deepcopy(msg), "delivery_id": key, "outbox_accepted_at": time.time()}
            await self.store.write(updated)
            self.document = updated
            return True

    async def acknowledge(self, key: str):
        async with self.lock:
            if key not in self.document["pending"]:
                return
            updated = copy.deepcopy(self.document)
            del updated["pending"][key]
            updated["acknowledged"].append(key)
            await self.store.write(updated)
            self.document = updated

    def first(self):
        return next(iter(self.document["pending"].items()), None)


class Outbound:
    def __init__(self) -> None:
        self.q: Optional[asyncio.Queue] = None
        self.task: Optional[asyncio.Task] = None
        self.sent = 0
        self.dropped = 0
        self.errors = 0
        self.retries = 0
        self.inflight = 0
        self.outbox = None
        self.store = None
        self.credential = None
        self.restore_lock = asyncio.Lock()
        self.wake = None

    @property
    def durable(self) -> bool:
        return bool(os.getenv("TOUCHLINE_OUTBOX_URL")) and self.enabled

    async def _restore(self):
        if not self.durable or self.outbox is not None:
            return
        async with self.restore_lock:
            if self.outbox is not None:
                return
            from azure.identity.aio import DefaultAzureCredential
            from touchline.journal import BlobJournalStore
            credential = DefaultAzureCredential()
            store = BlobJournalStore(os.environ["TOUCHLINE_OUTBOX_URL"], credential)
            outbox = DurableOutbox(store, {"namespace": os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE", "connection-string"),
                                          "hub": HUB})
            try:
                await outbox.restore()
            except BaseException:
                await store.close()
                await credential.close()
                raise
            self.outbox, self.store, self.credential = outbox, store, credential
            self.wake = asyncio.Event()

    async def start(self):
        if not self.enabled:
            return
        await self._restore()
        if self.q is None:
            self.q = asyncio.Queue(maxsize=2000)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())

    async def publish(self, msg: dict):
        """Durable mode returns only after storage commits; input replay repairs gaps."""
        if not self.durable:
            self.emit(msg)
            return
        await self.start()
        await self.outbox.enqueue(msg)
        self.wake.set()

    @property
    def enabled(self) -> bool:
        return os.getenv("TOUCHLINE_OUTBOUND", "on") != "off" and bool(
            os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE") or os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"))

    def status(self) -> dict:
        pending = list(self.outbox.document["pending"].values()) if self.outbox else []
        oldest = max((max(0, time.time() - msg.get("outbox_accepted_at", time.time())) for msg in pending), default=0)
        running = bool(self.task and not self.task.done())
        degraded = self.durable and (self.outbox is None or (bool(pending) and (not running or oldest > 120)))
        return {"enabled": self.enabled, "hub": HUB, "sent": self.sent, "dropped": self.dropped, "errors": self.errors,
                "degraded": degraded, "oldest_pending_seconds": round(oldest, 1),
                "retries": self.retries, "pending": len(self.outbox.document["pending"]) if self.outbox else
                (self.q.qsize() if self.q else 0) + self.inflight,
                "acknowledged": len(self.outbox.document["acknowledged"]) if self.outbox else 0,
                "outbox_ready": self.outbox is not None,
                "sender_running": running,
                "durability": "single-writer Blob outbox; at-least-once delivery with stable delivery_id" if self.durable else
                "process memory; retries while running, no durable outbound outbox"}

    def emit(self, msg: dict) -> None:
        if not self.enabled:
            return
        if self.durable:
            raise RuntimeError("Durable outbound requires await publish(), not fire-and-forget emit()")
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

    async def _deliver_durable(self, prod, key: str, msg: dict):
        await self._send(prod, msg)
        # A successful send followed by a failed acknowledgement must not repeatedly
        # republish the same message while this process is still alive. Retain it in
        # the durable ledger and retry only the acknowledgement. A process crash
        # still permits redelivery, which is why the contract remains at least once.
        while True:
            try:
                await self.outbox.acknowledge(key)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.errors += 1
                self.retries += 1
                log.warning("outbound sent; acknowledgement pending in storage: %s", exc)
                await asyncio.sleep(2)

    async def close(self, timeout=5):
        if self.task is None:
            return
        try:
            if self.outbox:
                async def drain():
                    while self.outbox.document["pending"]:
                        await asyncio.sleep(0.05)
                await asyncio.wait_for(drain(), timeout=timeout)
            else:
                await asyncio.wait_for(self.q.join(), timeout=timeout)
        except asyncio.TimeoutError:
            if not self.outbox:
                self.dropped += self.q.qsize() + self.inflight
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.task = self.q = None
        self.inflight = 0
        if self.store:
            await self.store.close()
            await self.credential.close()
            self.outbox = self.store = self.credential = self.wake = None
        self.restore_lock = asyncio.Lock()

    async def _run(self) -> None:  # pragma: no cover - needs Azure
        while True:
            try:
                await self._run_connection()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.errors += 1
                self.retries += 1
                log.warning("outbound connection failed; pending delivery retained: %s", exc)
                await asyncio.sleep(2)

    async def _run_connection(self) -> None:  # pragma: no cover - needs Azure
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
                    if self.outbox:
                        item = self.outbox.first()
                        if item is None:
                            self.wake.clear()
                            # No await between checking pending and clearing wake.
                            await self.wake.wait()
                            continue
                        key, msg = item
                        self.inflight = 1
                        await self._deliver_durable(prod, key, msg)
                        self.inflight = 0
                        continue
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
