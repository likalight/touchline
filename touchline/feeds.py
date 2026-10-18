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


def _consumer():
    from azure.eventhub.aio import EventHubConsumerClient

    group = os.getenv("TOUCHLINE_EVENTHUB_CONSUMER_GROUP", "$Default")
    if os.getenv("TOUCHLINE_EVENTHUB_CONNECTION"):
        return EventHubConsumerClient.from_connection_string(os.environ["TOUCHLINE_EVENTHUB_CONNECTION"], group, eventhub_name=HUB)
    from azure.identity.aio import DefaultAzureCredential

    return EventHubConsumerClient(os.environ["TOUCHLINE_EVENTHUB_NAMESPACE"], HUB, group, DefaultAzureCredential())


def eventhub_enabled() -> bool:
    return bool(os.getenv("TOUCHLINE_EVENTHUB_CONNECTION") or os.getenv("TOUCHLINE_EVENTHUB_NAMESPACE"))


async def eventhub_payloads(stop: Optional[asyncio.Event] = None) -> AsyncIterator[dict]:
    """Yield decoded JSON payloads from the hub (latest position), across all partitions."""
    q: asyncio.Queue = asyncio.Queue(maxsize=10000)
    client = _consumer()

    async def on_event(partition_context, event):
        if event is None:
            return
        try:
            q.put_nowait(json.loads(event.body_as_str()))
        except Exception as exc:  # malformed message: let the IngestGuard see something invalid
            q.put_nowait({"_invalid": str(exc)})

    task = asyncio.create_task(client.receive(on_event=on_event, starting_position="@latest"))
    try:
        while stop is None or not stop.is_set():
            try:
                yield await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
    finally:
        await client.close()
        task.cancel()


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
        await prod.send_batch([EventData(json.dumps({"meta": sim.meta.model_dump()}))], partition_key=sim.match_id)
        last = 0.0
        for ev in events:
            await asyncio.sleep(max(0.0, (ev.t - last) / speed))
            last = ev.t
            await prod.send_batch([EventData(ev.model_dump_json())], partition_key=sim.match_id)
    return len(events)
