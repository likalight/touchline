"""Viewer-created simulations retain local results without publishing into the shared outbox."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from touchline import server
from touchline.runtime import MatchSession


def test_public_created_match_finishes_without_outbound_but_preserves_local_results(monkeypatch):
    publish = AsyncMock()
    monkeypatch.setattr("touchline.runtime.outbound", SimpleNamespace(durable=True, publish=publish))
    monkeypatch.setattr(server, "sessions", {})

    async def run():
        result = await server.create_match(server.NewMatch(seed=87, speed=240))
        session = server.sessions[result["session_id"]]
        assert session.broadcast_outputs is False
        queue = session.subscribe()
        session.control("jump", 200)
        await asyncio.wait_for(session.task, timeout=30)
        assert session.done and session.state.status == "full_time"
        assert session.insights and all(i["verification"]["status"] == "verified" for i in session.insights)
        package = session.package()
        assert package["complete"] and package["score"] == {"home": 3, "away": 2}
        assert package["recaps"] and package["highlights"]
        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())
        assert {"hello", "insight", "state", "done"} <= {m["type"] for m in messages}
        publish.assert_not_awaited()

        # Isolation is specific to the public creation route, not global runtime behaviour.
        demo = server.new_demo()
        assert demo.broadcast_outputs is True
        await demo.stop()
        async def feed():
            if False:
                yield {}
        external = MatchSession(meta=session.meta, feed=feed(), match_id="live")
        assert external.broadcast_outputs is True
        await external.feed.aclose()

    asyncio.run(run())
