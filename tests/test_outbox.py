"""Durable acceptance, crash replay and at-least-once delivery contracts."""
import asyncio
from copy import deepcopy
from unittest.mock import patch

import pytest

from touchline.outbound import DurableOutbox, Outbound, delivery_key


class Store:
    def __init__(self):
        self.value = None
        self.fail = False

    async def read(self):
        return deepcopy(self.value)

    async def write(self, value):
        if self.fail:
            raise OSError("storage unavailable")
        self.value = deepcopy(value)


def message(i="I1", session="live"):
    return {"type": "insight", "match_id": "match-1", "session": session, "id": i,
            "kind": "goal", "evidence": ["E00359"], "copy": {"en": {"title": "Goal"}}}


def test_pending_survives_restart_and_acknowledged_replay_is_suppressed():
    async def run():
        store = Store()
        first = DurableOutbox(store, {"hub": "insights"})
        await first.restore()
        msg = message()
        assert await first.enqueue(msg)
        # No successful send yet: a fresh process must find the exact payload.
        restored = DurableOutbox(store, {"hub": "insights"})
        await restored.restore()
        key, pending = restored.first()
        assert key == pending["delivery_id"] == delivery_key(msg)
        assert pending["copy"] == msg["copy"]
        assert not await restored.enqueue(message(session="new-process"))
        await restored.acknowledge(key)
        again = DurableOutbox(store, {"hub": "insights"})
        await again.restore()
        assert again.first() is None
        assert not await again.enqueue(msg)
        assert await again.enqueue(message("I2"))
    asyncio.run(run())


def test_storage_failure_does_not_claim_durable_acceptance():
    async def run():
        store = Store()
        out = DurableOutbox(store, {})
        store.fail = True
        with pytest.raises(OSError):
            await out.enqueue(message())
        assert out.first() is None and store.value is None
        store.fail = False
        assert await out.enqueue(message())
    asyncio.run(run())


def test_send_before_failed_ack_may_redeliver_but_keeps_same_delivery_identity():
    async def run():
        store = Store()
        out = DurableOutbox(store, {})
        await out.enqueue(message())
        key, first_delivery = out.first()
        # Event Hubs accepted the send, but the following storage commit failed.
        store.fail = True
        with pytest.raises(OSError):
            await out.acknowledge(key)
        store.fail = False
        restored = DurableOutbox(store, {})
        await restored.restore()
        assert restored.first() == (key, first_delivery)
        await restored.acknowledge(key)
        assert restored.first() is None
    asyncio.run(run())


def test_outbox_rejects_other_source_and_never_evicts_acknowledged_ids():
    async def run():
        store = Store()
        out = DurableOutbox(store, {"hub": "one"})
        out.LIMIT = 1
        await out.enqueue(message())
        await out.acknowledge(delivery_key(message()))
        with pytest.raises(RuntimeError, match="ledger full"):
            await out.enqueue(message("I2"))
        assert not await out.enqueue(message())
        with pytest.raises(ValueError, match="different source"):
            await DurableOutbox(store, {"hub": "two"}).restore()
    asyncio.run(run())


def test_source_identity_ignores_process_session_but_separates_matches():
    assert delivery_key(message()) == delivery_key(message(session="another-process"))
    assert delivery_key(message()) != delivery_key({**message(), "match_id": "match-2"})
    assert delivery_key(message()) != delivery_key(message("I2"))
    with pytest.raises(ValueError):
        delivery_key({"type": "insight", "id": "I1"})


def test_committed_payload_is_immutable_from_callers():
    async def run():
        store = Store()
        out = DurableOutbox(store, {})
        msg = message()
        await out.enqueue(msg)
        msg["copy"]["en"]["title"] = "Tampered later"
        assert out.first()[1]["copy"]["en"]["title"] == "Goal"
        assert next(iter(store.value["pending"].values()))["copy"]["en"]["title"] == "Goal"
    asyncio.run(run())


def test_journal_replay_reconstructs_uncommitted_output_without_requeueing_acknowledged_history():
    from touchline.runtime import MatchSession
    from touchline.sim.engine import simulate

    meta, events = simulate(7)

    class Sink:
        durable = True

        def __init__(self, outbox):
            self.outbox = outbox

        async def publish(self, msg):
            await self.outbox.enqueue(msg)

    async def feed(replay):
        for event in events:
            yield {**event.model_dump(), "_replay": replay}

    async def run():
        store = Store()
        out = DurableOutbox(store, {})
        with patch("touchline.runtime.outbound", Sink(out)):
            initial = MatchSession(meta=meta, feed=feed(False), match_id="first-process")
            await initial._run()
        original = set(out.document["pending"])
        assert len(original) > 20
        # One item never reached the durable output boundary; another was pending
        # at the crash. All other deliveries were acknowledged before the crash.
        missing, pending = list(original)[:2]
        for key in original - {missing, pending}:
            await out.acknowledge(key)
        del store.value["pending"][missing]
        restored = DurableOutbox(store, {})
        await restored.restore()
        with patch("touchline.runtime.outbound", Sink(restored)):
            session = MatchSession(meta=meta, feed=feed(True), match_id="restored-process")
            await session._run()
        assert set(restored.document["pending"]) == {missing, pending}
        assert set(restored.document["acknowledged"]) == original - {missing, pending}
        assert session.state.score == initial.state.score
    asyncio.run(run())


def test_failed_acknowledgement_retries_storage_without_resending(monkeypatch):
    from types import SimpleNamespace

    sent, acknowledgements = [], []

    async def send(batch, **kwargs):
        sent.append(batch)

    async def acknowledge(key):
        acknowledgements.append(key)
        if len(acknowledgements) < 3:
            raise OSError("temporary acknowledgement storage failure")

    original_sleep = asyncio.sleep
    monkeypatch.setattr("touchline.outbound.asyncio.sleep", lambda _: original_sleep(0))
    outbound = Outbound()
    outbound.outbox = SimpleNamespace(acknowledge=acknowledge)
    asyncio.run(outbound._deliver_durable(SimpleNamespace(send_batch=send), "delivery-1", message()))
    assert len(sent) == 1 and acknowledgements == ["delivery-1"] * 3
    assert outbound.sent == 1 and outbound.retries == 2 and outbound.errors == 2
