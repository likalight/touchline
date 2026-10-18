"""Multi-agent orchestration on Microsoft Agent Framework workflows.

Per detected moment, one workflow run:

    MomentScout --> TacticalAnalyst --> FactChecker --+--> Narrator[casual]  --+
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
                                to="FactChecker")
            await ctx.send_message(ins)
        except Exception as exc:  # never break the live pipeline
            self.d.trace.record("TacticalAnalyst", mo.kind, (time.perf_counter() - t0) * 1000, "error", repr(exc))


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
                res.renders[lang] = self.d.narrator.render(ins, self.persona, lang)
            llm = get_llm()
            if llm.available and self.d.extra_langs:
                async def one(lang):
                    r = await self.d.narrator.render_llm(ins, self.persona, lang)
                    if r is None:
                        r = {**res.renders["en"], "lang": lang, "source": "fallback:en"}
                    res.renders[lang] = r
                await asyncio.gather(*(one(lg) for lg in sorted(self.d.extra_langs) if lg not in BANKS))
            res.status = "ok"
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
        ins["cue"] = cue
        ins["latency_ms"] = round((time.perf_counter() - ins.pop("_t0", t0)) * 1000, 2)
        status = "aired" if cue and cue["approval"] == "auto" else (cue["approval"] if cue else "dropped")
        self.d.trace.record("Producer", ins["id"], (time.perf_counter() - t0) * 1000, "ok",
                            f"cue {status}" + (f" on {cue['layer']}" if cue else ""))
        await ctx.yield_output(ins)


class MomentPipeline:
    """Builds the Agent Framework workflow once and runs it per moment."""

    def __init__(self, deps: Deps):
        self.d = deps
        a, v, p = AnalystExecutor(deps), VerifierExecutor(deps), ProducerExecutor(deps)
        narrators = [NarratorExecutor(deps, persona) for persona in PERSONAS]
        self.workflow = (WorkflowBuilder(start_executor=a, name="touchline-moment",
                                         description="Analyst -> FactChecker -> 4x Narrator -> Producer")
                         .add_edge(a, v)
                         .add_fan_out_edges(v, narrators)
                         .add_fan_in_edges(narrators, p)
                         .build())
        self._lock = asyncio.Lock()

    async def run(self, mo: Moment) -> Optional[dict]:
        # A workflow instance processes one run at a time; moments are queued in order.
        async with self._lock:
            res = await self.workflow.run(mo)
        outs = res.get_outputs()
        return outs[0] if outs else None

    @staticmethod
    def topology() -> dict:
        return {
            "nodes": ["IngestGuard", "MatchState", "MomentScout", "TacticalAnalyst", "FactChecker",
                      *[f"Narrator[{p}]" for p in PERSONAS], "Producer", "RecapWriter", "AskTheAnalyst"],
            "edges": [["IngestGuard", "MatchState"], ["MatchState", "MomentScout"], ["MomentScout", "TacticalAnalyst"],
                      ["TacticalAnalyst", "FactChecker"], *[["FactChecker", f"Narrator[{p}]"] for p in PERSONAS],
                      *[[f"Narrator[{p}]", "Producer"] for p in PERSONAS]],
            "framework": "Microsoft Agent Framework WorkflowBuilder (fan-out / fan-in)",
        }
