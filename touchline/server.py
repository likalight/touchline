"""FastAPI service: live match sessions, SSE stream, overlay cues, recaps, Q&A, audit, A2A."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request

from touchline.auth import actor, can_produce, principal, require_producer
from touchline.auth import mode as auth_mode
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from touchline.a2a import mount_a2a
from touchline.i18n import BANKS, LANGS
from touchline.llm import get_llm
from touchline.runtime import MatchSession
from touchline.telemetry import setup_telemetry

log = logging.getLogger("touchline")
WEB = Path(__file__).resolve().parents[1] / "web"
MAX_SESSIONS = int(os.getenv("TOUCHLINE_MAX_SESSIONS", "12"))
DEMO_SEED = int(os.getenv("TOUCHLINE_DEMO_SEED", "221"))  # 3-2 comeback, hat-trick, red card, 94th-minute winner
DEMO_SPEED = float(os.getenv("TOUCHLINE_DEMO_SPEED", "10"))

sessions: dict[str, MatchSession] = {}
DEMO = "demo"


def new_demo() -> MatchSession:
    s = MatchSession(seed=DEMO_SEED, speed=DEMO_SPEED, match_id=DEMO)
    sessions[DEMO] = s
    s.start()
    return s


async def hub_consumer():
    """Event-driven mode: build a `live` session from matches published to Azure Event Hubs."""
    from touchline.feeds import eventhub_payloads
    from touchline.schema import MatchMeta

    feed = eventhub_payloads()
    queue: asyncio.Queue = asyncio.Queue()

    async def pump():
        async for payload in feed:
            await queue.put(payload)

    asyncio.create_task(pump())

    async def session_feed():
        while True:
            payload = await queue.get()
            if "meta" in payload:  # a new match started on the hub: hand over to a new session
                await queue.put(payload)
                return
            yield payload

    while True:
        payload = await queue.get()
        if "meta" not in payload:
            continue
        s = MatchSession(meta=MatchMeta.model_validate(payload["meta"]), feed=session_feed(), match_id="live")
        sessions["live"] = s
        s.start()
        log.info("live Event Hubs session started for %s", s.meta.match_id)
        while not s.done and queue.empty():
            await asyncio.sleep(1)


async def demo_keeper():
    """Keep a live demo match running 24/7 (restart a fresh one a minute after full-time)."""
    while True:
        s = sessions.get(DEMO)
        if s is None or (s.done and time.time() - s.created > 60):
            if s is not None and s.done:
                await asyncio.sleep(60)
            new_demo()
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry()
    tasks = [asyncio.create_task(demo_keeper())]
    from touchline.feeds import eventhub_enabled
    if eventhub_enabled():
        tasks.append(asyncio.create_task(hub_consumer()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Touchline - explainable match intelligence", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")
mount_a2a(app, lambda: sessions.get(DEMO), os.getenv("TOUCHLINE_PUBLIC_URL", "http://localhost:8000"))


def get(sid: str) -> MatchSession:
    s = sessions.get(sid)
    if not s:
        raise HTTPException(404, "unknown session")
    return s


class NewMatch(BaseModel):
    seed: int = Field(7, ge=0, le=10_000_000)
    speed: float = Field(10, ge=0.5, le=240)
    chaos: float = Field(0.0, ge=0, le=0.3)
    mode: str = "auto"
    langs: list[str] = []


class Control(BaseModel):
    action: str
    value: Optional[object] = None


class Ask(BaseModel):
    question: str = Field(..., max_length=500)
    lang: str = "en"


class Decision(BaseModel):
    approve: bool


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/story", include_in_schema=False)
async def story():
    return FileResponse(WEB / "story.html")


@app.get("/reel", include_in_schema=False)
async def reel_page():
    return FileResponse(WEB / "reel.html")


@app.get("/overlay", include_in_schema=False)
async def overlay():
    return FileResponse(WEB / "overlay.html")


@app.get("/api/health")
async def health():
    from touchline.safety import safety
    from touchline.speech import speech

    return {"status": "ok", "sessions": len(sessions), "llm": get_llm().status(), "speech": speech.status(),
            "content_safety": safety.status(), "auth": auth_mode()}


@app.get("/api/i18n")
async def i18n():
    return {"languages": LANGS, "banks": BANKS}


@app.post("/api/matches")
async def create_match(body: NewMatch):
    done = [k for k, v in sessions.items() if v.done and k != DEMO]
    for k in done:
        sessions.pop(k, None)
    if len(sessions) >= MAX_SESSIONS:
        raise HTTPException(429, "too many live sessions")
    s = MatchSession(seed=body.seed, speed=body.speed, chaos=body.chaos, mode=body.mode, extra_langs=set(body.langs))
    sessions[s.id] = s
    s.start()
    return {"session_id": s.id, **{k: v for k, v in s.describe().items() if k != "match"}}


@app.get("/api/matches")
async def list_matches():
    return [{"session_id": k, "match_id": v.meta.match_id, "seed": v.seed, "minute": v.state.minute, "score": v.state.score,
             "done": v.done} for k, v in sessions.items()]


@app.get("/api/matches/{sid}")
async def match(sid: str):
    s = get(sid)
    return {**s.describe(), "state": s.snapshot()}


@app.get("/api/matches/{sid}/stream")
async def stream(sid: str, request: Request):
    s = get(sid)
    q = s.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {msg['type']}\ndata: {json.dumps(msg, separators=(',', ':'), default=str)}\n\n"
        finally:
            s.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


PRODUCER_ACTIONS = {"mode", "drill"}            # always producer tools
SHARED_ACTIONS = {"pause", "resume", "speed", "jump"}  # producer tools on the shared broadcast; free on a fan's own match


@app.get("/api/me")
async def me(request: Request):
    """Who is signed in (Microsoft Entra ID via Container Apps authentication) and what they may do."""
    p = principal(request)
    return {**p, "can_produce": can_produce(p), "login": "/.auth/login/aad", "logout": "/.auth/logout"}


@app.post("/api/matches/{sid}/control")
async def control(sid: str, body: Control, request: Request):
    s = get(sid)
    if body.action in PRODUCER_ACTIONS or (sid == DEMO and body.action in SHARED_ACTIONS):
        p = require_producer(request)
        s.actions.append({"at": time.time(), "minute": s.state.minute, "actor": actor(p), "action": body.action, "value": body.value})
    return s.control(body.action, body.value)


@app.get("/api/matches/{sid}/insights")
async def insights(sid: str, persona: Optional[str] = None, lang: str = "en", since: int = 0):
    s = get(sid)
    out = []
    for ins in s.insights[since:]:
        if persona:
            r = ins.get("renders", {}).get(persona, {}).get(lang)
            out.append({k: ins[k] for k in ("id", "kind", "minute", "t", "team", "salience", "event_ids")} | {"render": r})
        else:
            out.append(ins)
    return out


@app.get("/api/matches/{sid}/cues")
async def cues(sid: str):
    s = get(sid)
    return [i["cue"] for i in s.insights if i.get("cue")]


@app.post("/api/matches/{sid}/cues/{cue_id}/decision")
async def decide(sid: str, cue_id: str, body: Decision, request: Request):
    p = require_producer(request)
    s = get(sid)
    s.actions.append({"at": time.time(), "minute": s.state.minute, "actor": actor(p), "action": "approve" if body.approve else "drop", "value": cue_id})
    cue = s.decide_cue(cue_id, body.approve)
    if not cue:
        raise HTTPException(404, "cue not pending")
    return cue


@app.get("/api/matches/{sid}/recap")
async def recap(sid: str, persona: str = "casual", lang: str = "en"):
    s = get(sid)
    if lang not in BANKS:
        r = s.get_recap(persona, "en")
        if get_llm().available:
            rc = s.recap.frames()
            alt = await s.narrator.render_llm(rc, persona, lang)
            if alt:
                return {**r, **alt}
        return {**r, "note": f"'{lang}' needs an LLM backend; showing English"}
    return s.get_recap(persona, lang)


@app.post("/api/matches/{sid}/ask")
async def ask(sid: str, body: Ask):
    from touchline.safety import safety

    s = get(sid)
    t0 = time.perf_counter()
    refused = await safety.screen_question(body.question)
    if refused:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        s.trace.record("ContentSafety", "qa", ms, "blocked", f"{refused}: question refused before any agent saw it")
        return {"answer": "I can only help with questions about this match.", "citations": [], "source": "content_safety",
                "refused": refused, "ms": ms}
    res = await s.ask_agent.ask(body.question, body.lang)
    res["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    s.trace.record("AskTheAnalyst", "qa", res["ms"], note=f"{res['source']}: {body.question[:60]}")
    return res


@app.get("/api/matches/{sid}/players")
async def players(sid: str):
    s = get(sid)
    return [{**s.state.player_summary(pid), "rating": s.state.player_rating(pid)} for pid in s.state.players]


@app.get("/api/matches/{sid}/players/{pid}")
async def player(sid: str, pid: str):
    s = get(sid)
    if pid not in s.state.players:
        raise HTTPException(404, "unknown player")
    return {**s.state.player_summary(pid), "rating": s.state.player_rating(pid), "heatmap": s.state.heat[pid]}


@app.get("/api/matches/{sid}/events/{eid}")
async def event(sid: str, eid: str):
    s = get(sid)
    en = s.state.enriched.get(eid)
    if not en:
        raise HTTPException(404, "unknown or future event")
    out = {"facts": en.facts(), "event": en.ev.model_dump()}
    if en.ev.frame:
        from touchline.analytics.state import pitch_control
        out["pitch_control"] = pitch_control(en.ev.frame, s.state.pace)
    if en.xg_features:
        out["xg_explain"] = s.state.models.xg.explain(en.xg_features, s.state.models.shot_baseline)
    if en.pass_features:
        out["pass_explain"] = s.state.models.pass_.explain(en.pass_features, s.state.models.pass_baseline)
    return out


@app.get("/api/matches/{sid}/window")
async def window(sid: str, start: float, end: float):
    """Events (with player positions) for one slice of the match clock, for replays and 3D reels.
    Only events that have already happened are returned."""
    from touchline.runtime import Q_EVENT_KEYS

    s = get(sid)
    if end - start > 180 or end < start:
        raise HTTPException(400, "window must be 0-180 s of match time")
    score, out = {"home": 0, "away": 0}, []
    names = {pid: p.name for pid, p in s.state.players.items()}
    for ev in s.events:
        if ev.id not in s.state.enriched:
            break
        if ev.type == "goal" and ev.team:
            score[ev.team] += 1
        if ev.t < start:
            continue
        if ev.t > end:
            break
        out.append({"id": ev.id, "t": ev.t, "minute": ev.minute, "etype": ev.type, "team": ev.team,
                    "player_id": ev.player_id, "player": names.get(ev.player_id), "target_id": ev.target_id,
                    "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y, "outcome": ev.outcome,
                    "q": {k: ev.qualifiers[k] for k in Q_EVENT_KEYS if k in ev.qualifiers}, "frame": ev.frame,
                    "score": dict(score)})
    return {"start": start, "end": end, "events": out}


REELS: dict[str, dict] = {}
REEL_DIR = Path(os.getenv("TOUCHLINE_REEL_DIR", "/tmp/touchline-reels"))


def _check_reel_args(s, club, player):
    """club: home, away or both; player: one id or a comma-separated list of favourites (max 11)."""
    ids = sorted({p for p in (player or "").split(",") if p})
    if club not in (None, "", "home", "away", "both") or len(ids) > 11 or any(p not in s.state.players for p in ids):
        raise HTTPException(400, "unknown club or player")
    return ",".join(ids) or None


@app.get("/api/matches/{sid}/reel")
async def reel_plan(sid: str, club: Optional[str] = None, player: Optional[str] = None, lang: str = "en", persona: str = "casual"):
    """My Match: the personal highlights plan (an edit decision list on the match clock)."""
    from touchline.highlights import plan_reel

    s = get(sid)
    player = _check_reel_args(s, club, player)
    edl = plan_reel(s, club or None, player or None, lang, persona)
    key = f"{sid}:{s.meta.match_id}:{len(s.insights)}:{club}:{player}:{lang}:{persona}"
    job = REELS.get(key)
    edl["video"] = {"status": job["status"], "url": f"/api/reels/{job['id']}.mp4" if job["status"] == "ready" else None} if job else None
    edl["key"] = key
    return edl


@app.post("/api/matches/{sid}/reel")
async def reel_render(sid: str, club: Optional[str] = None, player: Optional[str] = None, lang: str = "en", persona: str = "casual"):
    """Render the personal reel to MP4 in the background (broadcast camera, burned-in graphics, optional voice)."""
    import uuid as _uuid

    from touchline.highlights import plan_reel, render_reel
    from touchline.speech import speech

    s = get(sid)
    player = _check_reel_args(s, club, player)
    key = f"{sid}:{s.meta.match_id}:{len(s.insights)}:{club}:{player}:{lang}:{persona}"
    if key in REELS:
        job = REELS[key]
        return {"id": job["id"], "status": job["status"], "url": f"/api/reels/{job['id']}.mp4" if job["status"] == "ready" else None}
    if sum(1 for j in REELS.values() if j["status"] == "rendering") >= 2:
        raise HTTPException(429, "two reels are already rendering; try again shortly")
    REEL_DIR.mkdir(parents=True, exist_ok=True)
    job = {"id": _uuid.uuid4().hex[:12], "status": "rendering", "started": time.time()}
    REELS[key] = job
    edl = plan_reel(s, club or None, player or None, lang, persona)

    async def go():
        try:
            voice = None
            if speech.available:
                voice = [await speech.synthesize(f"{c['title']}. {c['line']}", lang) for c in edl["clips"]]
            out = str(REEL_DIR / f"{job['id']}.mp4")
            await asyncio.to_thread(render_reel, s, edl, out, 25, 1280, 720, voice)
            job["status"] = "ready"
        except Exception as exc:  # pragma: no cover
            log.exception("reel failed")
            job["status"] = f"failed: {exc}"
    asyncio.create_task(go())
    return {"id": job["id"], "status": "rendering", "clips": len(edl["clips"])}


@app.get("/api/reels/{rid}.mp4", include_in_schema=False)
async def reel_file(rid: str):
    if not rid.isalnum():
        raise HTTPException(404)
    path = REEL_DIR / f"{rid}.mp4"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/speak")
async def speak(text: str, lang: str = "en", voice: str = "lead"):
    """Neural voice for audio description and commentary (Azure AI Speech). 503 when not configured."""
    from fastapi.responses import Response

    from touchline.speech import speech

    if not speech.available or len(text) > 600:
        raise HTTPException(503, "speech not configured")
    audio = await speech.synthesize(text, lang, "analyst" if voice == "analyst" else "lead")
    if not audio:
        raise HTTPException(503, "speech unavailable")
    return Response(audio, media_type="audio/mpeg")


@app.get("/api/matches/{sid}/package")
async def package(sid: str):
    """Post-match package (recaps x personas x languages, highlights edit list, top players, verification)."""
    return get(sid).package()


@app.get("/api/downstream")
async def downstream():
    """What the event-driven side has produced: the outbound stream and the packages Azure Function's output."""
    import httpx

    from touchline.outbound import outbound

    out = {"outbound": outbound.status(), "packages": None}
    url = os.getenv("TOUCHLINE_PACKAGES_URL")
    if url:
        try:
            async with httpx.AsyncClient(timeout=4) as c:
                out["packages"] = (await c.get(f"{url.rstrip('/')}/api/packages")).json()
        except Exception as exc:
            out["packages"] = {"error": str(exc)[:200]}
    return out


@app.get("/api/matches/{sid}/audit")
async def audit(sid: str):
    return get(sid).audit()


@app.get("/api/matches/{sid}/dataset.jsonl", response_class=PlainTextResponse)
async def dataset(sid: str):
    """The full synthetic event dataset for this match (data innovation: re-usable, seeded, schema-validated)."""
    s = get(sid)
    head = json.dumps({"meta": s.meta.model_dump()})
    return head + "\n" + "\n".join(e.model_dump_json() for e in s.events)


@app.get("/api/models")
async def models():
    from touchline.analytics.models import get_models
    p = get_models().params
    return {k: p[k] for k in ("version", "trained_on", "league")} | {
        "xg_eval": p["xg"]["eval"], "pass_eval": p["pass"]["eval"], "xt": p["xt"]}


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):  # pragma: no cover
    log.exception("unhandled error")
    return JSONResponse({"error": "internal error"}, status_code=500)
