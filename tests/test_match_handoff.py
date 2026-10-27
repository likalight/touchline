"""Next-match metadata cannot retire replay history before durable output acceptance."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from touchline.journal import InputJournal


class Store:
    def __init__(self):
        self.value = None
        self.writes = []
        self.before_write = lambda value: None

    async def read(self):
        return deepcopy(self.value)

    async def write(self, value):
        self.before_write(value)
        self.value = deepcopy(value)
        self.writes.append(deepcopy(value))

    async def close(self):
        pass


def test_input_journal_refuses_unacknowledged_replacement_and_retains_memory_on_failed_commit():
    async def run():
        store = Store()
        journal = InputJournal(store, {}, batch_size=1)
        await journal.append({"meta": {"match_id": "A"}}, "1")
        await journal.append({"id": "E1", "match_id": "A"}, "2")
        before = deepcopy(journal.document)
        with pytest.raises(ValueError, match="not acknowledged"):
            await journal.append({"meta": {"match_id": "B"}}, "3")
        assert journal.document == before == store.value
        with pytest.raises(ValueError, match="different"):
            journal.acknowledge_match("B")
        journal.acknowledge_match("A")
        def unavailable(value):
            raise OSError("storage unavailable")
        store.before_write = unavailable
        with pytest.raises(OSError):
            await journal.append({"meta": {"match_id": "B"}}, "3")
        assert journal.document == before == store.value
        store.before_write = lambda value: None
        await journal.append({"meta": {"match_id": "B"}}, "3")
        assert journal.document["meta"]["match_id"] == "B"
        assert journal.document["events"] == []
    asyncio.run(run())


@pytest.mark.parametrize("interrupted,restored,processor_failure", [
    (False, False, False), (True, False, False),
    (False, True, False), (True, True, False), (True, False, True),
])
def test_rapid_matches_wait_for_slow_processor_commit(monkeypatch, interrupted, restored, processor_failure):
    from touchline import feeds, server, journal as journal_module
    from touchline.sim.engine import simulate
    import azure.identity.aio

    first, _ = simulate(3)
    second, _ = simulate(4)
    meta_a, meta_b = first.model_dump(), second.model_dump()
    source = {"namespace": "example.servicebus.windows.net", "hub": feeds.HUB, "partition": "0", "group": "$Default"}
    events_a = [{"id": "A1", "match_id": first.match_id, "type": "pass"}]
    if not interrupted:
        events_a.append({"id": "A2", "match_id": first.match_id, "type": "full_time"})
    events_b = [{"id": "B1", "match_id": second.match_id, "type": "full_time"}]
    store = Store()
    if restored:
        store.value = {"schema": "touchline.journal/1", "source": source,
                       "meta": meta_a, "events": events_a, "offset": "10"}
    sessions = []
    closed = []

    class Credential:
        async def close(self):
            closed.append("credential")

    async def run():
        allow_commit, awaiting_commit = asyncio.Event(), asyncio.Event()
        first_committed, attempted_next = asyncio.Event(), asyncio.Event()

        def before_write(value):
            if value["meta"]["match_id"] == second.match_id:
                assert first_committed.is_set(), "metadata retired prior match before output committed"
        store.before_write = before_write

        class Client:
            async def receive(self, on_event, **kwargs):
                items = [] if restored else [{"meta": meta_a}, *events_a]
                items += [{"meta": meta_b}, *events_b]
                for offset, payload in enumerate(items, 11):
                    if payload.get("meta", {}).get("match_id") == second.match_id:
                        attempted_next.set()
                    await on_event(None, SimpleNamespace(body_as_str=lambda p=payload: json.dumps(p), offset=str(offset)))

            async def close(self):
                closed.append("client")

        class SlowSession:
            def __init__(self, meta, feed, match_id):
                self.meta, self.feed = meta, feed
                self.received = []
                sessions.append(self)

            def start(self):
                self.task = asyncio.create_task(self.process())

            async def process(self):
                async for payload in self.feed:
                    self.received.append(payload["id"])
                    if payload.get("type") == "full_time":
                        break
                if self.meta.match_id == first.match_id:
                    awaiting_commit.set()
                    await allow_commit.wait()
                    if processor_failure:
                        raise RuntimeError("outbox commit failed")
                    first_committed.set()

        monkeypatch.setattr(feeds, "_consumer", lambda credential: Client())
        monkeypatch.setattr(server, "MatchSession", SlowSession)
        consumer = asyncio.create_task(server.hub_consumer())
        await asyncio.wait_for(awaiting_commit.wait(), 3)
        await asyncio.wait_for(attempted_next.wait(), 3)
        assert store.value["meta"]["match_id"] == first.match_id
        assert not first_committed.is_set()
        allow_commit.set()
        if processor_failure:
            with pytest.raises(RuntimeError, match="outbox commit failed"):
                await asyncio.wait_for(consumer, 3)
            assert store.value["meta"]["match_id"] == first.match_id
            assert len(sessions) == 1
        else:
            await asyncio.wait_for(consumer, 3)
            assert [s.received for s in sessions] == [[e["id"] for e in events_a], ["B1"]]
            assert store.value["meta"]["match_id"] == second.match_id
        assert "client" in closed and "credential" in closed

    monkeypatch.setattr(azure.identity.aio, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(journal_module, "BlobJournalStore", lambda *args: store)
    monkeypatch.setattr(server, "sessions", {})
    monkeypatch.setenv("TOUCHLINE_INPUT_JOURNAL_URL", "https://example.blob.core.windows.net/input/journal.json")
    monkeypatch.setenv("TOUCHLINE_EVENTHUB_NAMESPACE", source["namespace"])
    asyncio.run(run())
