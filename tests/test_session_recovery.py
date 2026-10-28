"""Bounded snapshot recovery and private-session capacity, not lossless SSE replay."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from touchline.runtime import MatchSession


def drain(queue):
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    return messages


def test_all_old_private_sessions_expire_even_when_paused_or_unfinished(monkeypatch):
    from touchline import server

    now = time.time()
    def session(*, old=True, done=False, owned=False):
        return SimpleNamespace(created=now - (server.SESSION_TTL + 10 if old else 0),
                               done=done, paused=True, control_token="owner" if owned else None,
                               stop=AsyncMock())

    entries = {"paused": session(), "slow": session(), "done": session(done=True),
               "judge": session(owned=True), "fresh": session(old=False),
               "demo": session(), "live": session()}
    monkeypatch.setattr(server, "sessions", entries.copy())
    asyncio.run(server.prune_sessions())
    assert set(server.sessions) == {"fresh", "demo", "live"}
    for sid, value in entries.items():
        assert value.stop.await_count == (0 if sid in server.sessions else 1)


def test_reconnect_after_long_gap_restores_snapshot_bounded_history_and_completion():
    async def run():
        session = MatchSession(seed=87)
        session.broadcast_outputs = False
        first = session.subscribe()
        drain(first)
        for event in session.events[:50]:
            await session._play(event, realtime=True)
        before = {m["id"] for m in drain(first) if m["type"] == "event"}
        session.unsubscribe(first)
        for event in session.events[50:]:
            await session._play(event, realtime=True)
        await asyncio.gather(*list(session.pending_tasks), return_exceptions=True)
        session.done = True
        after = session.subscribe()
        messages = drain(after)
        assert messages[0]["recovery"]["lossless_event_replay"] is False
        assert messages[0]["done"] is True
        assert messages[1] == {"type": "state", **session.snapshot()}
        assert messages[1]["score"] == {"home": 3, "away": 2}
        events = [m for m in messages if m["type"] == "event"]
        assert len(events) == 20 and all(m["replayed"] for m in events)
        assert [m["id"] for m in events] == [e.id for e in session.events[-20:]]
        # Document the contract: a current snapshot replaces an arbitrary gap;
        # the transport does not pretend every missed event has been recovered.
        assert len(before | {m["id"] for m in events}) < len(session.events)
        history = [m for m in messages if m["type"] == "insight"]
        assert [m["insight"]["id"] for m in history] == [i["id"] for i in session.replay_history()]
        assert all(m["replayed"] for m in history)
        assert messages[-1] == {"type": "done", "replayed": True}
        session.unsubscribe(after)
        assert not session.subscribers
    asyncio.run(run())


def test_slow_consumer_gets_explicit_reset_without_stalling_healthy_viewer():
    session = MatchSession(seed=87)
    slow, healthy = session.subscribe(), session.subscribe()
    drain(slow)
    drain(healthy)
    while not slow.full():
        slow.put_nowait({"type": "obsolete"})
    session.publish({"type": "state", **session.snapshot()})
    recovered = drain(slow)
    assert recovered[0]["type"] == "hello"
    assert recovered[0]["recovery"]["reason"] == "slow_consumer"
    assert recovered[1] == {"type": "state", **session.snapshot()}
    assert not any(m["type"] == "obsolete" for m in recovered)
    assert drain(healthy) == [{"type": "state", **session.snapshot()}]
    session.publish({"type": "control", "action": "resume", "value": None})
    assert drain(slow) == drain(healthy) == [{"type": "control", "action": "resume", "value": None}]


def test_open_stream_follows_replaced_match_and_reports_private_expiry(monkeypatch):
    from touchline import server
    import json

    async def run():
        first = MatchSession(seed=87, match_id="demo")
        second = MatchSession(seed=91, match_id="demo")
        monkeypatch.setattr(server, "sessions", {"demo": first})
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        response = await server.stream("demo", request)
        stream = response.body_iterator
        assert await anext(stream) == "retry: 2000\n\n"
        assert 'SYN-00087' in await anext(stream)
        server.sessions["demo"] = second
        message = await anext(stream)
        assert message.startswith("event: hello\n") and 'SYN-00091' in message
        assert not first.subscribers and len(second.subscribers) == 1
        state = json.loads((await anext(stream)).split("data: ", 1)[1])
        assert state["score"] == second.snapshot()["score"]
        await stream.aclose()
        assert not second.subscribers

        private = MatchSession(seed=87)
        server.sessions[private.id] = private
        response = await server.stream(private.id, request)
        stream = response.body_iterator
        await anext(stream)
        del server.sessions[private.id]
        assert (await anext(stream)).startswith("event: session_expired\n")
        assert [part async for part in stream] == []
        assert not private.subscribers
    asyncio.run(run())
