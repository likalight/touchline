import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from touchline.judge import JudgeSession
from touchline.receipts import build_receipt


def test_judge_assets_are_compressed_and_decodable():
    from touchline import server
    client = TestClient(server.app)
    response = client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in response.headers["vary"]
    assert "async function boot()" in response.text


@pytest.fixture(scope="module")
def replay():
    async def run():
        session = JudgeSession()
        session.paused = False
        waits = []

        async def fast_wait(seconds):
            waits.append(seconds)
            await asyncio.sleep(0)

        session._wait = fast_wait
        with patch("touchline.runtime.outbound.emit") as emit:
            await session._run()
            emit.assert_not_called()
        return session, sum(waits)
    return asyncio.run(run())


def test_judge_replays_chronological_history_for_ninety_seconds(replay):
    session, seconds = replay
    assert seconds == pytest.approx(90)
    assert session.done and session.paused
    assert session.state.score == {"home": 3, "away": 2}
    assert session.guard.stats["accepted"] == len(session.state.events)
    assert session.guard.stats["duplicates"] == 0
    assert len(session.replay_history()) == 4
    goals = [i for i in session.insights if i["kind"] == "goal"]
    assert len(goals) == 5
    redemption = next(i for i in goals if "s.redemption" in i.get("storyline", []))
    texts = [line["text"] for line in redemption["renders"]["analyst"]["en"]["lines"]]
    assert any("redemption" in text.lower() for text in texts)
    for insight in session.insights:
        assert all(session.state.events[eid].t <= insight["t"] for eid in insight["event_ids"])


def test_receipt_keeps_original_verdict_and_handoffs(replay):
    session, _ = replay
    insight = next(i for i in session.insights if i["kind"] == "goal")
    before = session.checker.stats().copy()
    session.trace.spans.clear()  # long match: the receipt must not depend on the rolling log
    receipt = build_receipt(session, insight, "analyst", "es")
    assert receipt["render"]["lang"] == "es"
    assert receipt["verification"] == insight["verification"]
    assert session.checker.stats() == before  # inspecting is read-only
    assert {a["agent"] for a in receipt["agents"]} >= {"TacticalAnalyst", "StorylineKeeper", "FactChecker", "Producer"}
    assert {e["event_id"] for e in receipt["evidence"]} == set(insight["event_ids"])
    assert receipt["editorial"]["decision"] == insight["cue"]["decision"]
    assert "excludes" in receipt["timing_scope"]


def test_checker_challenge_rejects_tampering_without_mutating_match(replay):
    import copy
    from touchline.proof import challenge
    session, _ = replay
    insight = next(i for i in session.insights if i['kind'] == 'goal')
    before = copy.deepcopy(insight)
    counters = session.checker.stats().copy()
    result = challenge(session, insight)
    assert result['passed'] and result['original']['status'] == 'verified'
    assert result['altered']['status'] == 'blocked'
    assert any('xg mismatch' in issue for issue in result['altered']['issues'])
    assert result['source_value'] == round(session.state.enriched[result['event_id']].xg, 2)
    assert insight == before and session.checker.stats() == counters
    # A broken original must not be reported as a successful demonstration.
    wrong = copy.deepcopy(insight)
    next(f for f in wrong['reasons'] if f['k'] == 'r.chance_quality')['p']['xg'] = -1
    assert not challenge(session, wrong)['passed']


def test_checker_challenge_endpoint_is_bounded_to_delivered_insights(monkeypatch, replay):
    from touchline import server
    session, _ = replay
    monkeypatch.setitem(server.sessions, 'proof-test', session)
    client = TestClient(server.app)
    goal = next(i for i in session.insights if i['kind'] == 'goal')
    assert client.get(f"/api/matches/proof-test/insights/{goal['id']}/challenge").json()['passed']
    assert client.get('/api/matches/proof-test/insights/future/challenge').status_code == 404
    other = next(i for i in session.insights if not any(f['k'] == 'r.chance_quality' for f in i['reasons']))
    assert client.get(f"/api/matches/proof-test/insights/{other['id']}/challenge").status_code == 422


def test_story_map_preserves_original_coordinates_and_earlier_memory(replay):
    session, _ = replay
    redemption = next(i for i in session.insights if "s.redemption" in i.get("storyline", []))
    receipt = build_receipt(session, redemption)
    memory = next(c for c in receipt["claims"] if c["key"] == "s.redemption")
    assert len(memory["event_ids"]) == 2
    evidence = {e["event_id"]: e for e in receipt["evidence"]}
    assert evidence[memory["event_ids"][0]]["t"] < redemption["t"] - 60
    for eid, item in evidence.items():
        original = session.state.events[eid]
        assert item["t"] == original.t <= redemption["t"]
        assert item["position"] == {k: getattr(original, k) for k in ("x", "y", "end_x", "end_y")}
    chapters = session.describe()["judge"]["moments"]
    assert [c["event_id"] for c in chapters] == [c["event_id"] for c in session.chapters]


def test_judge_isolation_restart_and_receipt_endpoint(monkeypatch, replay):
    from touchline import server
    monkeypatch.setenv("TOUCHLINE_AUTH", "entra")
    with TestClient(server.app) as client:
        assert client.get("/judge").status_code == 200
        first = client.post("/api/judge").json()
        second = client.post("/api/judge").json()
        assert first["session_id"] != second["session_id"]
        assert "control_token" not in client.get(f"/api/matches/{first['session_id']}").json()
        sid = first["session_id"]
        headers = {"X-Touchline-Judge-Token": first["control_token"]}
        wrong = {"X-Touchline-Judge-Token": second["control_token"]}
        assert client.post(f"/api/matches/{sid}/control", json={"action": "resume"}).status_code == 403
        assert client.post(f"/api/matches/{sid}/control", json={"action": "resume"}, headers=wrong).status_code == 403
        assert client.post(f"/api/matches/{sid}/control", json={"action": "pause"}, headers=headers).status_code == 200
        assert client.post(f"/api/matches/{sid}/control", json={"action": "jump", "value": 90}, headers=headers).status_code == 400
        assert client.get(f"/api/matches/{sid}/insights/future/receipt").status_code == 404
        assert client.delete(f"/api/judge/{sid}", headers=wrong).status_code == 403
        assert client.delete(f"/api/judge/{sid}", headers=headers).status_code == 200
        assert client.get(f"/api/matches/{second['session_id']}").status_code == 200
        assert client.get("/api/matches/demo").status_code == 200
        # Read a fully processed fixture through the real HTTP route.
        session, _ = replay
        server.sessions[session.id] = session
        goal = next(i for i in session.insights if i["kind"] == "goal")
        response = client.get(f"/api/matches/{session.id}/insights/{goal['id']}/receipt")
        assert response.status_code == 200 and response.json()["schema"] == "touchline.receipt/1"


def test_abandoned_judge_sessions_expire(monkeypatch):
    from touchline import server

    async def run():
        session = JudgeSession()
        session.created -= server.SESSION_TTL + 1
        session.start()
        monkeypatch.setattr(server, "sessions", {session.id: session})
        await server.prune_sessions()
        assert not server.sessions and session.task.cancelled()
    asyncio.run(run())
