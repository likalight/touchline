"""API surface, A2A, and the real Agent Framework LLM path against a mock model."""
import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from touchline import llm as llm_mod


def test_api_and_a2a():
    from touchline.server import app

    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        sid = c.post("/api/matches", json={"seed": 3, "speed": 240}).json()["session_id"]
        c.post(f"/api/matches/{sid}/control", json={"action": "jump", "value": 50})
        time.sleep(1.5)
        st = c.get(f"/api/matches/{sid}").json()["state"]
        assert st["minute"] >= 1
        assert c.post(f"/api/matches/{sid}/ask", json={"question": "who is the best player?"}).json()["answer"]
        assert c.get(f"/api/matches/{sid}/recap?persona=casual&lang=es").json()["title"]
        lines = c.get(f"/api/matches/{sid}/dataset.jsonl").text.splitlines()
        assert len(lines) > 1000 and "meta" in json.loads(lines[0])
        card = c.get("/.well-known/agent-card.json").json()
        assert card["name"] and card["skills"]
        rpc = {"jsonrpc": "2.0", "id": 1, "method": "SendMessage",
               "params": {"message": {"messageId": "t1", "role": "ROLE_USER", "parts": [{"text": "What's the win probability?"}]}}}
        res = c.post("/a2a", json=rpc, headers={"A2A-Version": "1.0"}).json()
        assert "Win probability" in res["result"]["message"]["parts"][0]["text"]


# ---------------------------------------------------------------- mock OpenAI-compatible model
MODE = {"honest": True}
mock = FastAPI()


@mock.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    user = [m for m in body["messages"] if m["role"] == "user"][-1]["content"]
    if isinstance(user, list):
        user = " ".join(p.get("text", "") for p in user)
    data = json.loads(user[user.index("{"):user.rindex("}") + 1])
    if MODE["honest"]:
        out = {"title": data["title"].upper(), "lines": data["lines"]}
    else:
        out = {"title": data["title"], "lines": ["He has now scored 99 goals this season"]}
    return {"id": "x", "object": "chat.completion", "created": 0, "model": body.get("model", "mock"),
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(out)}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


@pytest.fixture(scope="module")
def mock_llm(monkeypatch_module):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(mock, port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        time.sleep(0.05)
    monkeypatch_module.setenv("TOUCHLINE_LLM", "on")
    monkeypatch_module.setenv("OPENAI_API_KEY", "test")
    monkeypatch_module.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch_module.setenv("OPENAI_MODEL", "mock-model")
    llm_mod.reset_llm()
    yield
    server.should_exit = True
    llm_mod.reset_llm()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_llm_narration_is_verified(mock_llm):
    from touchline.agents.analyst import TacticalAnalyst
    from touchline.agents.narrator import Narrator
    from touchline.agents.scout import MomentScout
    from touchline.agents.verifier import FactChecker
    from touchline.analytics.state import MatchState
    from touchline.sim.engine import simulate

    llm = llm_mod.get_llm()
    assert llm.backend == "openai_compatible"
    meta, evs = simulate(7)
    s = MatchState(meta)
    sc = MomentScout(s)
    an = TacticalAnalyst(s, sc)
    goal = None
    for e in evs:
        for mo in sc.observe(s.apply(e)):
            if mo.kind == "goal" and goal is None:
                goal = an.analyse(mo)
        if goal:
            break
    nr = Narrator(FactChecker(s))

    async def both():
        MODE["honest"] = True
        good = await nr.render_llm(goal, "casual", "ja")
        MODE["honest"] = False
        bad = await nr.render_llm(goal, "casual", "ja")
        return good, bad

    good, bad = asyncio.run(both())
    assert good and good["source"].startswith("llm:") and good["title"].isupper()
    assert bad is None  # hallucinated number rejected by the FactChecker, twice (with one corrective retry)
    assert nr.llm_rejected == 2
