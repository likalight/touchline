"""Multi-agent orchestration on Microsoft Agent Framework workflows.

Per detected moment, one workflow run:

    MomentScout --> TacticalAnalyst --> StorylineKeeper --> FactChecker --+--> Narrator[casual]  --+
                                                      +--> Narrator[analyst] --+--> Producer --> overlay cue
                                                      +--> Narrator[studio]  --+
                                                      +--> Narrator[access]  --+

* shared state: all executors read the same MatchState blackboard (read-only)
* handoffs: typed messages along workflow edges (Moment -> insight -> NarrationResult[])
* concurrency: the four narrators run in the same superstep (fan-out / fan-in)
* failure recovery: each executor catches its own failures; a failed narrator falls
  back to deterministic copy, a blocked insight never reaches air, LLM calls sit behind
  a circuit breaker, and every span is recorded for the audit trail
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from touchline.agents.analyst import TacticalAnalyst
from touchline.agents.narrator import PERSONAS, Narrator
from touchline.agents.producer import Producer
from touchline.agents.scout import Moment
from touchline.agents.verifier import FactChecker
from touchline.i18n import BANKS
from touchline.llm import get_llm


class Trace:
    """In-memory span log (also mirrored to OpenTelemetry when enabled)."""

    def __init__(self, maxlen: int = 2000):
        self.spans: deque = deque(maxlen=maxlen)
        self.listeners: list[Callable[[dict], None]] = []
        self._otel = None
        try:
            from opentelemetry import trace as ot

            self._otel = ot.get_tracer("touchline")
        except Exception:  # pragma: no cover
            pass

    def record(self, agent: str, ref: str, ms: float, status: str = "ok", note: str = "", to: Optional[str] = None):
        span = {"ts": time.time(), "agent": agent, "ref": ref, "ms": round(ms, 2), "status": status, "note": note,
                "handoff_to": to}
        self.spans.append(span)
        if self._otel is not None:
            with self._otel.start_as_current_span(f"touchline.{agent}") as sp:
                for k, v in span.items():
                    if v is not None:
                        sp.set_attribute(f"touchline.{k}", v)
        for fn in self.listeners:
            fn(span)


@dataclass
class NarrationResult:
    persona: str
    insight: dict
    renders: dict = field(default_factory=dict)
    ms: float = 0.0
    status: str = "ok"


@dataclass
class Deps:
    analyst: TacticalAnalyst
    checker: FactChecker
    narrator: Narrator
    producer: Producer
    trace: Trace
    extra_langs: set = field(default_factory=set)
    now_t: Callable[[], float] = lambda: 0.0
    storyline: object = None
    late: Optional[Callable] = None  # schedules slow renders off the hot path
    booth: object = None             # CommentaryBooth: two-voice commentary on each moment
    drills: dict = field(default_factory=dict)  # resilience drills: name -> moments remaining
    on_fault: Optional[Callable] = None         # runtime hook: a drill fault was detected (name, agent, note)


class AnalystExecutor(Executor):
    def __init__(self, deps: Deps):
        super().__init__(id="TacticalAnalyst")
        self.d = deps

    @handler
    async def run(self, mo: Moment, ctx: WorkflowContext[dict]) -> None:
        t0 = time.perf_counter()
        try:
            ins = self.d.analyst.analyse(mo)
            ins["_t0"] = t0
            self.d.trace.record("TacticalAnalyst", ins["id"], (time.perf_counter() - t0) * 1000,
                                note=f"{mo.kind}: {len(ins['reasons'])} reasons, {len(ins['event_ids'])} events cited",
                                to="StorylineKeeper")
            await ctx.send_message(ins)
        except Exception as exc:  # never break the live pipeline
            self.d.trace.record("TacticalAnalyst", mo.kind, (time.perf_counter() - t0) * 1000, "error", repr(exc))


class StorylineExecutor(Executor):
    """Adds match-long callbacks (errors, redemption, comebacks, keepers) to the analyst's insight."""

    def __init__(self, deps: "Deps"):
        super().__init__(id="StorylineKeeper")
        self.d = deps

    @handler
    async def run(self, ins: dict, ctx: WorkflowContext[dict]) -> None:
        t0 = time.perf_counter()
        added = []
        try:
            if self.d.drills.get("storyline_crash", 0) > 0:
                self.d.drills["storyline_crash"] -= 1
                raise RuntimeError("drill: StorylineKeeper crashed")
            if self.d.storyline is not None:
                added = self.d.storyline.callbacks(ins)
                if added:
                    # callbacks go straight after the headline facts so every persona sees them
                    ins["reasons"] = ins["reasons"][:2] + added + ins["reasons"][2:]
                    ins["event_ids"] = sorted(set(ins["event_ids"]) | {i for f in added for i in f["ev"]})
                    ins["storyline"] = [f["k"] for f in added]
        except Exception as exc:
            self.d.trace.record("StorylineKeeper", ins["id"], (time.perf_counter() - t0) * 1000, "error",
                                f"{exc}; moment continues without callbacks", to="FactChecker")
            ins.setdefault("degraded", []).append("storyline")
            if self.d.on_fault:
                self.d.on_fault("storyline_crash", "StorylineKeeper", "caught in the agent; the moment went on without storyline callbacks")
            await ctx.send_message(ins)
            return
        self.d.trace.record("StorylineKeeper", ins["id"], (time.perf_counter() - t0) * 1000,
                            note=f"{len(added)} callbacks" if added else "no thread applies", to="FactChecker")
        await ctx.send_message(ins)


class VerifierExecutor(Executor):
    def __init__(self, deps: Deps):
        super().__init__(id="FactChecker")
        self.d = deps

    @handler
    async def run(self, ins: dict, ctx: WorkflowContext[dict]) -> None:
        t0 = time.perf_counter()
        v = self.d.checker.check_insight(ins)
        ins["verification"] = v
        self.d.trace.record("FactChecker", ins["id"], (time.perf_counter() - t0) * 1000,
                            "ok" if v["status"] == "verified" else "blocked",
                            f"{v['checks']} checks" + (f"; {v['issues'][:2]}" if v["issues"] else ""),
                            to="Narrator x4" if v["status"] == "verified" else "Producer (drop)")
        await ctx.send_message(ins)


class NarratorExecutor(Executor):
    def __init__(self, deps: Deps, persona: str):
        super().__init__(id=f"Narrator[{persona}]")
        self.d = deps
        self.persona = persona

    @handler
    async def run(self, ins: dict, ctx: WorkflowContext[NarrationResult]) -> None:
        t0 = time.perf_counter()
        res = NarrationResult(self.persona, ins)
        if ins["verification"]["status"] == "verified":
            for lang in BANKS:
                try:
                    if self.persona == "analyst" and self.d.drills.get("narrator_crash", 0) > 0:
                        raise RuntimeError("drill: Narrator[analyst] crashed")
                    res.renders[lang] = self.d.narrator.render(ins, self.persona, lang)
                except Exception as exc:
                    # recover: a sibling persona's copy stands in, flagged, so the moment still airs everywhere
                    res.renders[lang] = {**self.d.narrator.render(ins, "studio", lang), "persona": self.persona, "source": "fallback:studio"}
                    res.status = "recovered"
                    if lang == "en":
                        self.d.trace.record(self.id, ins["id"], (time.perf_counter() - t0) * 1000, "error",
                                            f"{exc}; studio copy stands in", to="Producer")
                        if self.d.on_fault:
                            self.d.on_fault("narrator_crash", self.id, "caught; the studio narrator's verified copy stood in")
            if self.persona == "analyst" and self.d.drills.get("narrator_crash", 0) > 0:
                self.d.drills["narrator_crash"] -= 1
            if self.persona == "casual" and self.d.drills.get("hallucination", 0) > 0:
                # the same check every language-model line goes through: a fabricated figure must never air
                self.d.drills["hallucination"] -= 1
                fake = res.renders["en"]["title"] + ", his 99th goal of the season"
                issues = self.d.checker.check_text(ins, [fake])
                self.d.trace.record("FactChecker", ins["id"], 0.1, "blocked" if issues else "ok",
                                    f"rejected a generated line: {issues[:1]}" if issues else "missed a fabricated line",
                                    to=self.id)
                if self.d.on_fault:
                    self.d.on_fault("hallucination", "FactChecker",
                                    f"blocked \"{fake}\" ({next((i for i in issues if '99' in str(i)), issues[0]) if issues else 'not caught'}); the verified copy aired")
            llm = self.d.narrator.llm
            if llm.available and self.d.extra_langs and self.d.late is not None:
                for lg in sorted(self.d.extra_langs):
                    if lg in BANKS:
                        continue
                    res.renders[lg] = {**res.renders["en"], "lang": lg, "source": "pending"}

                    async def one(lang=lg, persona=self.persona, base=dict(ins)):
                        r = await self.d.narrator.render_llm(base, persona, lang)
                        return base["id"], persona, lang, r

                    self.d.late(one())
            res.status = "ok" if res.status != "recovered" else "recovered"
        else:
            res.status = "skipped"
        res.ms = (time.perf_counter() - t0) * 1000
        self.d.trace.record(self.id, ins["id"], res.ms, res.status, f"{len(res.renders)} languages", to="Producer")
        await ctx.send_message(res)


class ProducerExecutor(Executor):
    def __init__(self, deps: Deps):
        super().__init__(id="Producer")
        self.d = deps

    @handler
    async def run(self, results: list[NarrationResult], ctx: WorkflowContext[None, dict]) -> None:
        t0 = time.perf_counter()
        ins = results[0].insight
        ins["renders"] = {r.persona: r.renders for r in results if r.renders}
        cue = self.d.producer.schedule(ins, self.d.now_t())
        if self.d.booth is not None:
            ins["commentary"] = self.d.booth.exchange(ins)
        ins["cue"] = cue
        ins["latency_ms"] = round((time.perf_counter() - ins.pop("_t0", t0)) * 1000, 2)
        dec = (cue or {}).get("decision") or {}
        note = f"{dec.get('action', 'drop')} ({dec.get('score', 0):.2f}): {dec.get('reason', 'not verified')}" if cue else "dropped: not verified"
        self.d.trace.record("Producer", ins["id"], (time.perf_counter() - t0) * 1000, "ok", note)
        await ctx.yield_output(ins)


class MomentPipeline:
    """Builds the Agent Framework workflow once and runs it per moment."""

    def __init__(self, deps: Deps):
        self.d = deps
        a, st, v, p = AnalystExecutor(deps), StorylineExecutor(deps), VerifierExecutor(deps), ProducerExecutor(deps)
        narrators = [NarratorExecutor(deps, persona) for persona in PERSONAS]
        self.workflow = (WorkflowBuilder(start_executor=a, name="touchline-moment",
                                         description="Analyst -> Storyline -> FactChecker -> 4x Narrator -> Producer")
                         .add_edge(a, st)
                         .add_edge(st, v)
                         .add_fan_out_edges(v, narrators)
                         .add_fan_in_edges(narrators, p)
                         .build())
        self._lock = asyncio.Lock()
        self.restarts = 0

    def _build(self):
        d = self.d
        a, st, v, p = AnalystExecutor(d), StorylineExecutor(d), VerifierExecutor(d), ProducerExecutor(d)
        narrators = [NarratorExecutor(d, persona) for persona in PERSONAS]
        return (WorkflowBuilder(start_executor=a, name="touchline-moment",
                                description="Analyst -> Storyline -> FactChecker -> 4x Narrator -> Producer")
                .add_edge(a, st).add_edge(st, v).add_fan_out_edges(v, narrators).add_fan_in_edges(narrators, p).build())

    async def run(self, mo: Moment) -> Optional[dict]:
        # A workflow instance processes one run at a time; moments are queued in order.
        # Supervisor: if a run fails outright, rebuild the workflow and retry the moment once.
        async with self._lock:
            for attempt in range(2):
                t0 = time.perf_counter()
                try:
                    res = await self.workflow.run(mo)
                    outs = res.get_outputs()
                    return outs[0] if outs else None
                except Exception as exc:
                    self.restarts += 1
                    self.d.trace.record("Supervisor", getattr(mo, "kind", "moment"), (time.perf_counter() - t0) * 1000, "error",
                                        f"workflow failed ({exc}); rebuilt and {'retrying' if attempt == 0 else 'dropped the moment'}")
                    self.workflow = self._build()
        return None

    @staticmethod
    def topology() -> dict:
        return {
            "nodes": ["IngestGuard", "MatchState", "MomentScout", "TacticalAnalyst", "StorylineKeeper", "FactChecker",
                      *[f"Narrator[{p}]" for p in PERSONAS], "Producer", "CommentaryBooth", "RecapWriter", "AskTheAnalyst"],
            "edges": [["IngestGuard", "MatchState"], ["MatchState", "MomentScout"], ["MomentScout", "TacticalAnalyst"],
                      ["TacticalAnalyst", "StorylineKeeper"], ["StorylineKeeper", "FactChecker"],
                      *[["FactChecker", f"Narrator[{p}]"] for p in PERSONAS],
                      *[[f"Narrator[{p}]", "Producer"] for p in PERSONAS], ["Producer", "CommentaryBooth"]],
            "framework": "Microsoft Agent Framework WorkflowBuilder (fan-out / fan-in)",
        }
