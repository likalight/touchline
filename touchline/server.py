"""FastAPI service: live match sessions, SSE stream, overlay cues, recaps, Q&A, audit, A2A."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request

from touchline.auth import actor, can_produce, principal, require_producer
from touchline.mcp_server import build as build_mcp
from touchline.auth import mode as auth_mode
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, field_validator

from touchline.a2a import mount_a2a
from touchline.i18n import BANKS, LANGS
from touchline.llm import get_llm
from touchline.runtime import MatchSession
from touchline.telemetry import setup_telemetry

log = logging.getLogger("touchline")
WEB = Path(__file__).resolve().parents[1] / "web"
MAX_SESSIONS = int(os.getenv("TOUCHLINE_MAX_SESSIONS", "12"))
SESSION_TTL = 15 * 60
SUPPORTED_LANGUAGES = set(LANGS) | {"de", "ja", "hi", "ar", "zh", "ta", "sw"}
from touchline.demo import DEMO_SEED as DEFAULT_DEMO_SEED
DEMO_SEED = int(os.getenv("TOUCHLINE_DEMO_SEED", str(DEFAULT_DEMO_SEED)))
DEMO_SPEED = float(os.getenv("TOUCHLINE_DEMO_SPEED", "10"))

sessions: dict[str, MatchSession] = {}
feed_health = {"status": "disabled"}
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

    completed = asyncio.Event()
    completed.set()
    feed = eventhub_payloads(completed=completed)
    queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
    pending_meta = None
    exhausted = False

    async def pump():
        try:
            async for payload in feed:
                await queue.put(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Event Hubs feed stopped")
            raise
        finally:
            # Cancellation must not block shutdown on a full queue.
            if not asyncio.current_task().cancelling():
                await queue.put(None)

    pump_task = asyncio.create_task(pump())

    async def session_feed():
        nonlocal pending_meta, exhausted
        while True:
            payload = await queue.get()
            if payload is None:
                exhausted = True
                return
            if "_match_boundary" in payload:
                return  # drain pending work before the input journal can be replaced
            if "meta" in payload:  # a new match started on the hub: hand over to a new session
                pending_meta = payload  # do not move metadata behind its events in the queue
                return
            yield payload

    try:
        while True:
            if exhausted:
                await pump_task  # surface receive errors instead of silently stopping
                return
            payload = pending_meta if pending_meta is not None else await queue.get()
            pending_meta = None
            if payload is None:
                await pump_task
                return
            if "meta" not in payload:
                continue
            s = MatchSession(meta=MatchMeta.model_validate(payload["meta"]), feed=session_feed(), match_id="live")
            sessions["live"] = s
            s.start()
            log.info("live Event Hubs session started for %s", s.meta.match_id)
            # Only session_feed reads events until this match ends. Competing readers lose events.
            await s.task
            completed.set()  # runtime has accepted every output durably, or raised
    finally:
        pump_task.cancel()
        await asyncio.gather(pump_task, return_exceptions=True)
        await feed.aclose()  # also close when cancellation happened between yielded payloads


async def demo_keeper():
    """Keep a live demo match running 24/7 (restart a fresh one a minute after full-time)."""
    while True:
        await prune_sessions()
        s = sessions.get(DEMO)
        if s is None or (s.done and time.time() - s.created > 60):
            if s is not None and s.done:
                await asyncio.sleep(60)
            new_demo()
        await asyncio.sleep(5)


async def supervised_feed():
    feed_health.update(status="running")
    try:
        await hub_consumer()
        feed_health.update(status="stopped")
    except Exception as exc:
        feed_health.update(status="failed", error=type(exc).__name__)
        log.exception("Live feed stopped; inspect the input journal and connection before restarting")


class _MCPApp:
    """The MCP endpoint, rebuilt on each app start (its session manager can only run once per instance)."""

    def __init__(self) -> None:
        self.app = None

    async def __call__(self, scope, receive, send):
        if self.app is None:
            raise HTTPException(503, "starting")
        await self.app(scope, receive, send)


MCP_APP = _MCPApp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from touchline.feeds import eventhub_enabled
    from touchline.outbound import outbound

    setup_telemetry()
    await outbound.start()
    sessions.clear()
    feed_health.clear()
    feed_health.update(status="disabled")
    tasks = [asyncio.create_task(demo_keeper())]
    if eventhub_enabled():
        tasks.append(asyncio.create_task(supervised_feed()))
    mcp = build_mcp(lambda: sessions)
    MCP_APP.app = mcp.streamable_http_app()
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for s in list(sessions.values()):
            await s.stop()
        sessions.clear()
        from touchline.outbound import outbound
        await outbound.close()


app = FastAPI(title="Touchline - explainable match intelligence", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
from touchline.limits import PublicWorkLimits
app.add_middleware(PublicWorkLimits)
app.mount("/static", StaticFiles(directory=WEB), name="static")
mount_a2a(app, lambda: sessions.get(DEMO), os.getenv("TOUCHLINE_PUBLIC_URL", "http://localhost:8000"))


def get(sid: str) -> MatchSession:
    s = sessions.get(sid)
    if not s:
        raise HTTPException(404, "unknown session")
    return s


async def prune_sessions():
    for sid, s in list(sessions.items()):
        if (sid not in (DEMO, "live") and time.time() - s.created > SESSION_TTL
                and (s.done or getattr(s, "control_token", None))):
            await s.stop()
            sessions.pop(sid, None)


def judge_owner(s, request: Request):
    token = getattr(s, "control_token", None)
    if token and not secrets.compare_digest(request.headers.get("x-touchline-judge-token", ""), token):
        raise HTTPException(403, "This replay belongs to another viewer. Start your own Judge Mode.")


class NewMatch(BaseModel):
    seed: int = Field(7, ge=0, le=10_000_000)
    speed: float = Field(10, ge=0.5, le=240)
    chaos: float = Field(0.0, ge=0, le=0.3)
    mode: str = "auto"
    langs: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("langs")
    @classmethod
    def supported_languages(cls, value):
        if any(code not in SUPPORTED_LANGUAGES for code in value):
            raise ValueError("Choose supported language codes")
        return value


class Control(BaseModel):
    action: str
    value: Optional[object] = None


class Ask(BaseModel):
    question: str = Field(..., max_length=500)
    lang: str = Field("en", pattern=r"^[a-z]{2}$")


class Decision(BaseModel):
    approve: bool


class Feedback(BaseModel):
    insight_id: str = Field(..., max_length=40)
    useful: bool
    persona: str = Field("casual", max_length=12)
    lang: str = Field("en", max_length=8)


@app.get("/", include_in_schema=False)
@app.get("/judge", include_in_schema=False)
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/story", include_in_schema=False)
async def story():
    return FileResponse(WEB / "story.html")


@app.get("/phone", include_in_schema=False)
async def phone_page():
    return FileResponse(WEB / "phone.html")


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
    from touchline.outbound import outbound

    output = outbound.status()
    return {"status": "degraded" if feed_health["status"] in {"failed", "stopped"} or output["degraded"] else "ok",
            "feed": dict(feed_health), "sessions": len(sessions), "llm": get_llm().status(), "speech": speech.status(),
            "content_safety": safety.status(), "auth": auth_mode(), "outbound": output}


@app.get("/api/i18n")
async def i18n():
    return {"languages": LANGS, "banks": BANKS}


@app.get("/api/ready")
async def ready():
    ok = DEMO in sessions and feed_health["status"] not in {"failed", "stopped"}
    return JSONResponse({"ready": ok, "feed": dict(feed_health)}, status_code=200 if ok else 503)


@app.post("/api/matches")
async def create_match(body: NewMatch):
    await prune_sessions()
    if len(sessions) >= MAX_SESSIONS:
        raise HTTPException(429, "too many live sessions")
    s = MatchSession(seed=body.seed, speed=body.speed, chaos=body.chaos, mode=body.mode, extra_langs=set(body.langs))
    sessions[s.id] = s
    s.start()
    return {"session_id": s.id, **{k: v for k, v in s.describe().items() if k != "match"}}


@app.post("/api/judge")
async def create_judge():
    from touchline.judge import JudgeSession

    await prune_sessions()
    if len(sessions) >= MAX_SESSIONS:
        raise HTTPException(429, "All replay slots are busy. Please try again shortly.")
    s = JudgeSession()
    sessions[s.id] = s
    # Playback begins only when the creating browser is connected and sends resume.
    s.start()
    return {"session_id": s.id, "control_token": s.control_token, "duration_s": 90}


@app.delete("/api/judge/{sid}")
async def delete_judge(sid: str, request: Request):
    s = get(sid)
    if not getattr(s, "control_token", None):
        raise HTTPException(404, "unknown judge replay")
    judge_owner(s, request)
    await s.stop()
    sessions.pop(sid, None)
    return {"ok": True}


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
SHARED_ACTIONS = {"pause", "resume", "speed", "jump", "langs"}


@app.get("/api/me")
async def me(request: Request):
    """Who is signed in (Microsoft Entra ID via Container Apps authentication) and what they may do."""
    p = principal(request)
    protected = os.getenv("TOUCHLINE_PROTECT_SHARED", "").lower() == "on" and auth_mode() != "entra"
    identity = auth_mode() == "entra" and os.getenv("TOUCHLINE_TRUST_AUTH_PROXY", "").lower() == "on"
    return {**p, "can_produce": can_produce(p), "shared_read_only": protected,
            "can_control_shared": can_produce(p) and not protected,
            "identity_provider_configured": identity,
            "login": "/.auth/login/aad" if identity else None,
            "logout": "/.auth/logout" if identity else None}


@app.post("/api/matches/{sid}/control")
async def control(sid: str, body: Control, request: Request):
    s = get(sid)
    judge_owner(s, request)
    if body.action == "langs" and (not isinstance(body.value, list) or len(body.value) > 3
                                  or any(not isinstance(code, str) or code not in SUPPORTED_LANGUAGES for code in body.value)):
        raise HTTPException(422, "Choose at most three supported languages.")
    if getattr(s, "control_token", None) and body.action not in {"pause", "resume", "langs"}:
        raise HTTPException(400, "Judge Mode supports pause, resume and language selection. Use Restart to replay.")
    shared = sid in (DEMO, "live")
    if shared and os.getenv("TOUCHLINE_PROTECT_SHARED", "").lower() == "on" and auth_mode() != "entra":
        raise HTTPException(403, "The shared broadcast is read-only. Start Judge Mode for your own replay.")
    if body.action in PRODUCER_ACTIONS or (shared and body.action in SHARED_ACTIONS):
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


@app.get("/api/matches/{sid}/insights/{insight_id}/receipt")
async def receipt(sid: str, insight_id: str, persona: str = "casual", lang: str = "en"):
    from touchline.receipts import build_receipt

    s = get(sid)
    ins = next((i for i in s.insights if i["id"] == insight_id), None)
    if ins is None:
        raise HTTPException(404, "unknown or future insight")
    return build_receipt(s, ins, persona, lang)


@app.get("/api/matches/{sid}/cues")
async def cues(sid: str):
    s = get(sid)
    return [i["cue"] for i in s.insights if i.get("cue")]


@app.get("/api/matches/{sid}/insights/{insight_id}/challenge")
async def checker_challenge(sid: str, insight_id: str):
    from touchline.proof import challenge

    s = get(sid)
    ins = next((i for i in s.insights if i['id'] == insight_id), None)
    if ins is None:
        raise HTTPException(404, 'unknown or future insight')
    try:
        return challenge(s, ins)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/matches/{sid}/cues/{cue_id}/decision")
async def decide(sid: str, cue_id: str, body: Decision, request: Request):
    if sid in (DEMO, "live") and os.getenv("TOUCHLINE_PROTECT_SHARED", "").lower() == "on" and auth_mode() != "entra":
        raise HTTPException(403, "The shared broadcast is read-only.")
    p = require_producer(request)
    s = get(sid)
    judge_owner(s, request)
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
        if r.get("verification", {}).get("status") != "verified":
            return r
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
    s.trace.record("AskTheAnalyst", "qa", res["ms"], note=f"{res['source']}: question answered; input text not retained")
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


class WhatIf(BaseModel):
    scenario: str = Field(..., max_length=60)


@app.get("/api/matches/{sid}/whatif")
async def whatif_scenarios(sid: str):
    """Suggested counterfactuals from this match: every goal and red card so far, plus an extra goal for either side."""
    from touchline.whatif import scenarios

    return {"scenarios": scenarios(get(sid))}


@app.post("/api/matches/{sid}/whatif")
async def whatif_run(sid: str, body: WhatIf):
    """Replay the rest of the match 1,000 times with one thing changed, and compare."""
    from touchline.whatif import run

    s = get(sid)
    t0 = time.perf_counter()
    out = await asyncio.to_thread(run, s, body.scenario)
    if out is None:
        raise HTTPException(404, "unknown scenario")
    s.trace.record("WhatIf", body.scenario, (time.perf_counter() - t0) * 1000, note=out["summary"][:90])
    return out


@app.post("/api/matches/{sid}/feedback")
async def feedback(sid: str, body: Feedback):
    """A viewer says whether a graphic was useful: the evidence behind the impact claims."""
    return get(sid).add_feedback(body.insight_id, body.useful, body.persona, body.lang)


@app.get("/api/matches/{sid}/feedback")
async def feedback_summary(sid: str):
    return get(sid).feedback_summary()


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


# MCP for GitHub Copilot and other agents, at /mcp. Mounted last so every route above takes precedence.
app.mount("/", MCP_APP)
