"""MatchSession - runs one live (replayed) synthetic match through the agent pipeline
and broadcasts everything to subscribers (SSE clients, overlay renderers, A2A)."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from typing import Optional

from touchline.agents.ask import AskTheAnalyst
from touchline.agents.analyst import TacticalAnalyst
from touchline.agents.ingest import FaultInjector, IngestGuard
from touchline.agents.narrator import Narrator
from touchline.agents.producer import Producer
from touchline.agents.booth import CommentaryBooth
from touchline.agents.recap import RecapWriter
from touchline.agents.scout import MomentScout
from touchline.agents.storyline import StorylineKeeper
from touchline.agents.verifier import FactChecker
from touchline.analytics.models import get_models
from touchline.analytics.state import MatchState
from touchline.llm import get_llm
from touchline.orchestrator import Deps, MomentPipeline, Trace
from typing import AsyncIterator

from touchline.schema import Event, MatchMeta
from touchline.sim.engine import MatchSimulator

Q_EVENT_KEYS = ("distance_m", "ball_speed_kmh", "shot_speed_kmh", "speed_kmh", "pass_type", "body_part", "height")


def percentile(xs: list[float], p: float) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(p * len(s)))], 2)


class MatchSession:
    def __init__(self, seed: int = 7, speed: float = 12.0, chaos: float = 0.0, mode: str = "auto",
                 extra_langs: Optional[set] = None, match_id: Optional[str] = None,
                 meta: Optional[MatchMeta] = None, feed: Optional[AsyncIterator[dict]] = None):
        self.id = match_id or f"m-{uuid.uuid4().hex[:8]}"
        self.feed = feed
        if meta is not None:  # external, event-driven feed (e.g. Azure Event Hubs)
            self.meta, self.events = meta, []
        else:
            sim = MatchSimulator(seed, match_id=f"SYN-{seed:05d}")
            self.meta = sim.meta
            self.events = list(sim.run())
        self.seed, self.speed, self.chaos = seed, speed, chaos
        self.created = time.time()
        self.state = MatchState(self.meta)
        self.scout = MomentScout(self.state)
        self.checker = FactChecker(self.state)
        self.narrator = Narrator(self.checker)
        self.analyst = TacticalAnalyst(self.state, self.scout)
        self.storyline = StorylineKeeper(self.state)
        self.analyst.storyline = self.storyline
        self.checker.storyline = self.storyline
        self.producer = Producer(self.meta.match_id, mode=mode)
        self.recap = RecapWriter(self.state, self.narrator)
        self.recap.storyline = self.storyline
        self.guard = IngestGuard()
        self.injector = FaultInjector(chaos, seed)
        self.trace = Trace()
        self.insights: list[dict] = []
        self.ask_agent = AskTheAnalyst(self.state, lambda: self.insights)
        self.extra_langs = set(extra_langs or [])
        self.deps = Deps(self.analyst, self.checker, self.narrator, self.producer, self.trace, self.extra_langs,
                         now_t=lambda: self.state.t, storyline=self.storyline, late=self._late_render,
                         booth=CommentaryBooth(self.state.players, {"home": self.meta.home.name, "away": self.meta.away.name}))
        self.pipeline = MomentPipeline(self.deps)
        self.deps.on_fault = self._on_fault
        self.drills: list[dict] = []
        self._storm_left = 0
        self.subscribers: set[asyncio.Queue] = set()
        self.recent_events: deque = deque(maxlen=40)
        self.latencies: deque = deque(maxlen=500)
        self.event_latency: deque = deque(maxlen=2000)
        self.paused = False
        self.jump_to: Optional[int] = None
        self.task: Optional[asyncio.Task] = None
        self.clock_t = 0.0
        self.done = False
        self.recaps: dict[str, dict] = {}
        self.pending_tasks: set[asyncio.Task] = set()
        self.trace.listeners.append(lambda span: self.publish({"type": "trace", **span}))

    # ------------------------------------------------------------------ bus
    def publish(self, msg: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # slow consumer: drop rather than stall the live pipeline

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self.subscribers.add(q)
        q.put_nowait({"type": "hello", **self.describe()})
        q.put_nowait({"type": "state", **self.snapshot()})
        for e in list(self.recent_events)[-20:]:
            q.put_nowait(e)
        for span in list(self.trace.spans)[-30:]:
            q.put_nowait({"type": "trace", **span})
        for ins in self.insights[-30:]:
            q.put_nowait({"type": "insight", "insight": ins, "replayed": True})  # history: feed only, no graphics
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    # ------------------------------------------------------------------ views
    def describe(self) -> dict:
        return {"session_id": self.id, "match": self.meta.model_dump(), "seed": self.seed, "speed": self.speed,
                "chaos": self.chaos, "mode": self.producer.mode, "total_events": len(self.events), "done": self.done,
                "topology": MomentPipeline.topology(), "llm": get_llm().status(),
                "models": {"version": get_models().params["version"], "trained_on": get_models().params["trained_on"]}}

    def snapshot(self) -> dict:
        snap = self.state.snapshot()
        snap["drills"] = [self._public_drill(d) for d in self.drills[-8:]]
        snap["speed"] = self.speed
        snap["paused"] = self.paused
        snap["timeline"] = self.state.timeline[-120:]
        snap["players"] = {pid: {"rating": self.state.player_rating(pid), "top_speed_kmh": round(self.state.pl[pid]["top_speed_kmh"], 1),
                                 "xg": round(self.state.pl[pid]["xg"], 2), "xt": round(self.state.pl[pid]["xt_added"], 3),
                                 "passes": int(self.state.pl[pid]["passes"]), "completed": int(self.state.pl[pid]["completed"]),
                                 "distance_km": round(self.state.pl[pid]["distance_m"] / 1000, 2)}
                           for pid in self.state.players}
        snap["ops"] = self.ops()
        return snap

    def ops(self) -> dict:
        lat = list(self.latencies)
        ev_lat = list(self.event_latency)
        return {
            "insights": len(self.insights), "pipeline_ms_p50": percentile(lat, 0.5), "pipeline_ms_p95": percentile(lat, 0.95),
            "event_ms_p50": percentile(ev_lat, 0.5), "event_ms_p95": percentile(ev_lat, 0.95),
            "ingest": self.guard.stats, "fault_injection": self.injector.injected, "verifier": self.checker.stats(),
            "producer": self.producer.stats(), "llm": get_llm().status(),
            "narrator_llm": {"accepted": self.narrator.llm_ok, "rejected": self.narrator.llm_rejected},
        }

    def event_msg(self, ev: Event, en) -> dict:
        return {
            "type": "event", "id": ev.id, "seq": ev.seq, "t": ev.t, "minute": ev.minute, "period": ev.period,
            "etype": ev.type, "team": ev.team, "player_id": ev.player_id, "player": en.player_name,
            "target_id": ev.target_id, "target": en.target_name, "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y,
            "outcome": ev.outcome, "q": {k: ev.qualifiers[k] for k in Q_EVENT_KEYS if k in ev.qualifiers},
            "frame": ev.frame, "xg": round(en.xg, 3) if en.xg is not None else None,
            "difficulty": round(en.difficulty * 100) if en.difficulty is not None else None,
            "xt": round(en.xt_added, 3) if en.xt_added else 0, "bypassed": en.bypassed,
            "score": dict(self.state.score), "momentum": en.momentum, "phase": en.phase,
            "wp": {k: round(v, 3) for k, v in en.wp_after.items()},
        }

    # ------------------------------------------------------------------ run loop
    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        if self.feed is not None:
            async for payload in self.feed:
                for ev in self.guard.push(payload):
                    self.events.append(ev)
                    await self._play(ev, realtime=True)
                    if ev.type == "full_time":
                        break
                if self.state.status == "full_time":
                    break
            await asyncio.gather(*list(self.pending_tasks), return_exceptions=True)
            self.done = True
            self.publish({"type": "done"})
            return
        for payload in self.injector.apply(self.events):
            for ev in self.guard.push(payload):
                await self._play(ev)
        for ev in self.guard.flush():
            await self._play(ev)
        await asyncio.gather(*list(self.pending_tasks), return_exceptions=True)
        self.done = True
        self.publish({"type": "state", **self.snapshot()})
        self.publish({"type": "done"})

    async def _play(self, ev: Event, realtime: bool = False) -> None:
        jumping = self.jump_to is not None and ev.minute < self.jump_to and not realtime
        if self.jump_to is not None and not jumping:
            self.jump_to = None
        if realtime:
            pass  # the feed itself is paced by the real match clock
        elif not jumping:
            gap = max(0.0, ev.t - self.clock_t)
            remaining = gap / max(self.speed, 0.1)
            while remaining > 0:
                step = min(remaining, 0.25)
                await asyncio.sleep(step)
                if not self.paused:
                    remaining -= step
                if self.jump_to is not None:
                    break
            while self.paused:
                await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(0)
        self.clock_t = ev.t
        t0 = time.perf_counter()
        en = self.state.apply(ev)
        moments = self.scout.observe(en) + self.storyline.observe(en)
        self.event_latency.append((time.perf_counter() - t0) * 1000)
        msg = self.event_msg(ev, en)
        self.recent_events.append(msg)
        if not jumping:
            self.publish(msg)
        for mo in moments:
            # Analysis runs in step with the feed (~10 ms), so an insight can never read state from its future.
            # Slow LLM work (extra languages) is scheduled separately and arrives as a `render` update.
            await self._process(mo, jumping)
        if ev.seq % 12 == 0 or ev.type in ("goal", "half_time", "full_time", "card") or moments:
            if not jumping or ev.seq % 120 == 0:
                self.publish({"type": "state", **self.snapshot()})
        for cue in self.producer.expire() + self.producer.tick():
            self._update_cue(cue)
        if self.drills:
            if self._storm_left > 0:
                self._storm_left -= 1
            self._drill_tick()

    def _late_render(self, coro) -> None:
        """Run slow (LLM) renders off the hot path; publish each as it lands."""
        async def run():
            ins_id, persona, lang, render = await coro
            for ins in self.insights:
                if ins["id"] == ins_id and render:
                    ins.setdefault("renders", {}).setdefault(persona, {})[lang] = render
                    self.publish({"type": "render", "insight_id": ins_id, "persona": persona, "lang": lang, "render": render})
        task = asyncio.create_task(run())
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)

    async def _process(self, mo, jumping: bool) -> None:
        ins = await self.pipeline.run(mo)
        if ins is None:
            return
        self.latencies.append(ins["latency_ms"])
        self.insights.append(ins)
        if ins["kind"] in ("half_time", "full_time"):
            self.recaps.clear()
        self.publish({"type": "insight", "insight": ins, "replayed": jumping})
        if self.drills:
            self._drill_tick(ins)

    # ------------------------------------------------------------------ controls
    def control(self, action: str, value=None) -> dict:
        if action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "speed":
            self.speed = max(0.5, min(240.0, float(value)))
        elif action == "jump":
            target = int(value)
            if target > self.state.minute:
                self.jump_to = target
        elif action == "mode":
            self.producer.mode = "review" if value == "review" else "auto"
        elif action == "drill":
            return self.start_drill(str(value))
        elif action == "langs":
            self.extra_langs.clear()
            self.extra_langs.update(l for l in (value or []) if isinstance(l, str) and len(l) <= 8)
        self.publish({"type": "control", "action": action, "value": value})
        return {"ok": True, "speed": self.speed, "paused": self.paused, "mode": self.producer.mode}

    def _update_cue(self, cue: dict) -> None:
        for ins in reversed(self.insights):
            if ins.get("cue") and ins["cue"]["cue_id"] == cue["cue_id"]:
                ins["cue"] = cue
                break
        self.publish({"type": "cue_update", "cue": cue})

    # ------------------------------------------------------------------ resilience drills
    DRILLS = {
        "feed_storm": "Corrupt the feed", "llm_outage": "Take the language model down", "narrator_crash": "Crash a narrator",
        "storyline_crash": "Crash the storyline agent", "hallucination": "Inject a made-up number",
    }

    def start_drill(self, name: str) -> dict:
        if name not in self.DRILLS:
            raise ValueError("unknown drill")
        if any(d["name"] == name and not d["recovered"] for d in self.drills):
            return {"ok": False, "reason": "already running"}
        entry = {"id": f"D{len(self.drills) + 1}", "name": name, "label": self.DRILLS[name], "minute": self.state.minute,
                 "started": time.time(), "detected": None, "detected_by": None, "recovered": None, "ms": None, "notes": []}
        if name == "feed_storm":
            self.injector.rate = 0.35
            self._storm_left = 60
            entry["_guard0"] = dict(self.guard.stats)
        elif name == "llm_outage":
            get_llm().breaker.force_open(25)
            entry.update(detected=time.time(), detected_by="CircuitBreaker")
            entry["notes"].append("model marked unavailable; narrators and the analyst switched to verified phrase banks"
                                  if get_llm().client is not None else "no model configured here, so the app already runs on verified phrase banks")
        else:
            self.deps.drills[name] = 1 if name == "hallucination" else 2
        self.drills.append(entry)
        self._publish_drill(entry)
        return {"ok": True, "drill": self._public_drill(entry)}

    def _public_drill(self, d: dict) -> dict:
        return {k: v for k, v in d.items() if not k.startswith("_")}

    def _publish_drill(self, d: dict) -> None:
        self.publish({"type": "drill", "drill": self._public_drill(d)})

    def _on_fault(self, name: str, agent: str, note: str) -> None:
        for d in self.drills:
            if d["name"] == name and not d["recovered"]:
                if not d["detected"]:
                    d.update(detected=time.time(), detected_by=agent)
                if note not in d["notes"]:
                    d["notes"].append(note)
                self._publish_drill(d)

    def _drill_tick(self, after_insight: Optional[dict] = None) -> None:
        for d in self.drills:
            if d["recovered"]:
                continue
            n = d["name"]
            done = False
            if n == "feed_storm":
                g0, g = d["_guard0"], self.guard.stats
                caught = {k: g.get(k, 0) - g0.get(k, 0) for k in ("quarantined", "duplicates", "reordered")}
                if any(caught.values()) and not d["detected"]:
                    d.update(detected=time.time(), detected_by="IngestGuard")
                if self._storm_left <= 0 and d["detected"]:
                    self.injector.rate = self.chaos
                    d["notes"] = [f"{caught['quarantined']} malformed events quarantined, {caught['duplicates']} duplicates dropped, "
                                  f"{caught['reordered']} re-ordered; every real event applied exactly once, in order"]
                    done = True
            elif n == "llm_outage":
                done = not get_llm().breaker.open
                if done:
                    d["notes"].append("breaker closed again; model calls allowed (any failure re-opens it)")
            elif after_insight is not None and d["detected"] and self.deps.drills.get(n, 0) == 0 and not after_insight.get("degraded"):
                done = True
                d["notes"].append("next moment ran the full pipeline cleanly")
            if done:
                d["recovered"] = time.time()
                d["ms"] = round((d["recovered"] - d["started"]) * 1000)
                self._publish_drill(d)

    def decide_cue(self, cue_id: str, approve: bool) -> Optional[dict]:
        cue = self.producer.decide(cue_id, approve, self.state.t)
        if cue:
            for ins in self.insights:
                if ins.get("cue") and ins["cue"]["cue_id"] == cue_id:
                    ins["cue"] = cue
            self.publish({"type": "cue_update", "cue": cue})
        return cue

    def get_recap(self, persona: str, lang: str) -> dict:
        key = f"{self.state.minute}:{persona}:{lang}"
        if key not in self.recaps:
            self.recaps[key] = self.recap.render(persona, lang)
        return self.recaps[key]

    def audit(self) -> dict:
        return {"session": self.id, "match_id": self.meta.match_id, "synthetic": True, "seed": self.seed,
                "ops": self.ops(), "quarantine": self.guard.quarantine[-20:], "spans": list(self.trace.spans)[-200:],
                "insights": [{"id": i["id"], "kind": i["kind"], "minute": i["minute"], "verification": i["verification"],
                              "evidence": i["event_ids"], "latency_ms": i["latency_ms"],
                              "cue": i["cue"]["approval"] if i.get("cue") else None} for i in self.insights]}
