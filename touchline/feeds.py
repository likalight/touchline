"""Event-driven ingestion via Azure Event Hubs (optional).

In production the match feed does not come from an in-process simulator: a provider
publishes events to Event Hubs and Touchline consumes them. `scripts/publish_feed.py`
plays a synthetic match onto a hub in real time; with `TOUCHLINE_EVENTHUB_NAMESPACE`
(managed identity) or `TOUCHLINE_EVENTHUB_CONNECTION` set, the server consumes the hub
and runs a session called `live` through the same IngestGuard -> agents pipeline.

Wire format: JSON messages, the first `{"meta": MatchMeta}` then one `Event` per message.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncIterator, Optional

log = logging.getLogger("touchline.feeds")
HUB = os.getenv("TOUCHLINE_EVENTHUB_NAME", "match-events")


def _consumer(credential=None):
    from azure.eventhub.aio import EventHubConsumerClient

    group = os.getenv("TOUCHLINE_EVENTHUB_CONSUMER_GROUP", "$Default")
    if os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"):
        return EventHubConsumerClient.from_connection_string(os.environ["TOUCHLINE_EVENTHUB_CONNECTION"], group, eventhub_name=HUB)
    return EventHubConsumerClient(os.environ["TOUCHLINE_EVENTHUB_NAMESPACE"], HUB, group, credential)


def eventhub_enabled() -> bool:
    return bool(os.getenv("TOUCHLINE_EVENTHUB_CONNECTION") or os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE"))


async def eventhub_payloads(stop: Optional[asyncio.Event] = None,
                            completed: Optional[asyncio.Event] = None) -> AsyncIterator[dict]:
    """Resume one journaled partition; otherwise receive new events from all partitions.

    The journal commits the offset with the complete current match history. On restart,
    that history rebuilds state before live reception. Before the next match replaces
    the journal, an internal boundary ends even an interrupted match and the receiver
    waits for the processor's completion signal (including durable output commits).
    """
    from azure.identity.aio import DefaultAzureCredential
    from touchline.journal import BlobJournalStore, InputJournal

    q: asyncio.Queue = asyncio.Queue(maxsize=10000)
    credential = DefaultAzureCredential()
    client = _consumer(credential)
    store = journal = None
    task = None
    failure = None
    options = {"starting_position": "@latest"}

    async def on_event(partition_context, event):
        nonlocal failure
        if failure:
            return
        if event is None:
            return
        try:
            payload = json.loads(event.body_as_str())
            if not isinstance(payload, dict):
                raise ValueError("message must be a JSON object")
        except (ValueError, TypeError) as exc:
            payload = {"_invalid": str(exc)}
        if journal:
            try:
                if "meta" in payload:
                    if journal.document["meta"]:
                        previous = journal.document["meta"]["match_id"]
                        # Do not put new metadata in the journal/queue yet. The
                        # boundary lets a partial match flush and finish, avoiding
                        # a deadlock when its source never sent full_time.
                        if not completed.is_set():
                            await q.put({"_match_boundary": previous})
                        await completed.wait()
                        journal.acknowledge_match(previous)
                    completed.clear()
                await journal.append(payload, str(event.offset))
            except Exception as exc:
                failure = exc  # SDK callbacks can swallow exceptions; stop reception explicitly.
                return
        # Apply backpressure rather than treating QueueFull as malformed data and losing events.
        await q.put(payload)

    try:
        url = os.getenv("TOUCHLINE_INPUT_JOURNAL_URL")
        if url:
            if completed is None:
                raise ValueError("Journaled ingestion requires a processor completion signal")
            partition = os.getenv("TOUCHLINE_EVENTHUB_PARTITION", "0")
            store = BlobJournalStore(url, credential)
            journal = InputJournal(store, {"namespace": os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE", "connection-string"),
                                          "hub": HUB, "partition": partition,
                                          "group": os.getenv("TOUCHLINE_EVENTHUB_CONSUMER_GROUP", "$Default")})
            saved = await journal.restore()
            if saved["meta"]:
                completed.clear()
                yield {"meta": saved["meta"], "_replay": True}
                for payload in saved["events"]:
                    yield {**payload, "_replay": True}
            options = {"partition_id": partition, "starting_position": saved["offset"] if saved["offset"] is not None else "-1",
                       "starting_position_inclusive": False}
        task = asyncio.create_task(client.receive(on_event=on_event, **options))
        while stop is None or not stop.is_set():
            if failure:
                raise failure
            if task.done() and q.empty():
                await task  # receive/auth/storage errors must reach the health monitor
                return
            try:
                yield await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await client.close()
        if store:
            await store.close()
        await credential.close()


async def publish_match(seed: int, speed: float = 1.0) -> int:
    """Play a synthetic match onto Event Hubs at `speed` x real time."""
    from azure.eventhub import EventData
    from azure.eventhub.aio import EventHubProducerClient

    from touchline.sim.engine import MatchSimulator

    if os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"):
        prod = EventHubProducerClient.from_connection_string(os.environ["TOUCHLINE_EVENTHUB_CONNECTION"], eventhub_name=HUB)
    else:
        from azure.identity.aio import DefaultAzureCredential

        prod = EventHubProducerClient(os.environ["TOUCHLINE_EVENTHUB_NAMESPACE"], HUB, DefaultAzureCredential())
    sim = MatchSimulator(seed)
    events = list(sim.run())
    async with prod:
        partition = os.getenv("TOUCHLINE_EVENTHUB_PARTITION", "0")
        await prod.send_batch([EventData(json.dumps({"meta": sim.meta.model_dump()}))], partition_id=partition)
        last = 0.0
        for ev in events:
            await asyncio.sleep(max(0.0, (ev.t - last) / speed))
            last = ev.t
            await prod.send_batch([EventData(ev.model_dump_json())], partition_id=partition)
    return len(events)
