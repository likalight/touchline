"""Bounded external SSE experiment against one newly created, isolated synthetic match.

Example (run only after the target deployment is ready):
  python scripts/cloud_soak.py --base-url https://DEPLOYMENT --clients 12 --speed 30

No shared-match mutations, admin identity, LLM calls, retry storm or capacity extrapolation.
Every client stays in the denominator, including failed connections. The source is the
server's complete planned dataset, never the union of events observed by clients.
Normal synthetic-match insights and the final package use the configured outbound pipeline.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evidence_provenance import provenance


@dataclass
class Observation:
    client: int
    hello: bool = False
    done: bool = False
    error: str | None = None
    final_score: dict | None = None
    arrivals: dict[str, float] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    duplicates: int = 0


def source_dataset(text: str, seed: int) -> tuple[dict, list[dict]]:
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not rows or "meta" not in rows[0]:
        raise ValueError("dataset lacks match metadata")
    meta, events = rows[0]["meta"], rows[1:]
    if meta.get("seed") != seed or meta.get("synthetic") is not True:
        raise ValueError("dataset does not describe the requested synthetic seed")
    if not events or len(events) > 10000 or events[-1].get("type") != "full_time":
        raise ValueError("dataset is not a bounded complete match")
    ids = [e["id"] for e in events]
    if len(ids) != len(set(ids)) or [e["seq"] for e in events] != list(range(1, len(events) + 1)):
        raise ValueError("source event identities or sequence are invalid")
    if any(e.get("match_id") != meta["match_id"] for e in events):
        raise ValueError("dataset mixes match identities")
    return meta, events


def expected_score(events: list[dict]) -> dict:
    return {side: sum(e["type"] == "goal" and e.get("team") == side for e in events)
            for side in ("home", "away")}


def summarize(events: list[dict], observations: list[Observation], before_pause: set[str]) -> dict:
    expected = [e["id"] for e in events]
    source, positions = set(expected), {eid: i for i, eid in enumerate(expected)}
    score = expected_score(events)
    rows = []
    for client in observations:
        received = set(client.arrivals)
        missing, unexpected = source - received, received - source
        order = [positions[eid] for eid in client.order if eid in positions]
        ordered = all(a < b for a, b in zip(order, order[1:]))
        passed = (client.hello and client.done and not client.error and not missing and not unexpected
                  and not client.duplicates and ordered and client.final_score == score)
        rows.append({"client": client.client, "connected": client.hello, "done": client.done,
                     "error": client.error, "expected": len(source), "received_source_events": len(received & source),
                     "missing_ids": sorted(missing, key=positions.get), "unexpected_ids": sorted(unexpected),
                     "duplicates": client.duplicates, "source_order_preserved": ordered,
                     "final_score": client.final_score, "score_matches": client.final_score == score,
                     "passed": bool(passed), "arrival_ms": client.arrivals, "received_order": client.order})
    # Startup events may be replayed to staggered subscribers; keep them in the
    # completeness denominator but do not describe their receipt spread as live fanout.
    eligible = [eid for eid in expected if eid not in before_pause]
    spreads = [max(c.arrivals[eid] for c in observations) - min(c.arrivals[eid] for c in observations)
               for eid in eligible if observations and all(eid in c.arrivals for c in observations)]
    spreads.sort()
    percentile = lambda p: round(spreads[max(0, math.ceil(len(spreads) * p) - 1)], 3) if spreads else None
    all_received = set().union(*(set(c.arrivals) for c in observations)) if observations else set()
    passed_count = sum(r["passed"] for r in rows)
    return {"source_event_count": len(source), "expected_final_score": score,
            "clients_attempted": len(observations), "clients_connected": sum(c.hello for c in observations),
            "clients_passed": passed_count, "complete_client_share": passed_count / len(observations) if observations else 0,
            "all_clients_lost_ids": [eid for eid in expected if eid not in all_received],
            "fanout_receipt_spread": {"p50_ms": percentile(.5), "p95_ms": percentile(.95),
                                      "max_ms": round(max(spreads), 3) if spreads else None,
                                      "events_observed_by_every_client": len(spreads), "eligible_source_events": len(eligible),
                                      "scope": "Same observer machine: latest minus earliest client receipt of each post-start event. Not server latency or end-to-end latency."},
            "clients": rows, "passed": bool(source) and bool(observations) and passed_count == len(observations)}


async def messages(response):
    """Parse complete SSE frames, including multiline data and keep-alive comments."""
    kind, data = None, []
    async for line in response.aiter_lines():
        if not line:
            if data:
                payload = json.loads("\n".join(data))
                if not isinstance(payload, dict):
                    raise ValueError("SSE payload is not an object")
                yield kind or payload.get("type"), payload
            kind, data = None, []
        elif line.startswith("event:"):
            kind = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


async def receive(client, base, sid, match_id, observation, ready, started):
    try:
        async with client.stream("GET", f"{base}/api/matches/{sid}/stream",
                                 timeout=httpx.Timeout(45, connect=15, pool=15)) as response:
            response.raise_for_status()
            async for kind, payload in messages(response):
                if kind == "hello":
                    if payload.get("session_id") != sid or payload.get("match", {}).get("match_id") != match_id:
                        raise ValueError("SSE hello identifies a different match")
                    observation.hello = True
                    ready.set()
                elif kind == "event":
                    eid = payload["id"]
                    observation.order.append(eid)
                    if eid in observation.arrivals:
                        observation.duplicates += 1
                    else:
                        observation.arrivals[eid] = round((time.perf_counter() - started) * 1000, 3)
                elif kind == "state":
                    observation.final_score = payload.get("score")
                elif kind == "done":
                    observation.done = True
                    return
            observation.error = "stream_closed_before_done"
    except asyncio.CancelledError:
        if not observation.done and observation.error is None:
            observation.error = "cancelled_at_run_deadline_or_setup_failure"
        raise
    except Exception as exc:
        observation.error = type(exc).__name__
    finally:
        ready.set()  # failed clients remain visible; never stall the startup barrier forever


async def finish_isolated(control) -> str:
    """Best effort, bounded cleanup; a failed jump must not prevent resuming."""
    outcomes = {}
    try:
        async with asyncio.timeout(9):
            for action, value in (("jump", 200), ("resume", None)):
                try:
                    # Leave time for the second action even if the first stalls.
                    async with asyncio.timeout(4):
                        await control(action, value)
                    outcomes[action] = "accepted"
                except Exception as exc:
                    outcomes[action] = type(exc).__name__
    except Exception as exc:
        outcomes["cleanup"] = type(exc).__name__
    return ("Isolated completion requested; completion is not verified. "
            "Completed sessions are removed by the existing server TTL. " + json.dumps(outcomes, sort_keys=True))


async def experiment(args) -> dict:
    base = args.base_url.rstrip("/")
    started = time.perf_counter()
    observations = [Observation(i + 1) for i in range(args.clients)]
    tasks, events, before_pause = [], [], set()
    sid, meta, error, final_state = None, {}, None, {}
    initial_state, cleanup, dataset_sha = {}, "not_needed", None
    limits = httpx.Limits(max_connections=args.clients + 3, max_keepalive_connections=args.clients + 3)
    async with httpx.AsyncClient(limits=limits, timeout=20, follow_redirects=False) as client:
        async def control(action, value=None):
            response = await client.post(f"{base}/api/matches/{sid}/control", json={"action": action, "value": value})
            response.raise_for_status()
            return response.json()

        try:
            # Reserve nine seconds for bounded cleanup so even a failed run stays below ten minutes.
            async with asyncio.timeout(args.timeout_seconds - 10):
                response = await client.post(f"{base}/api/matches", json={"seed": args.seed, "speed": .5,
                                                                                         "chaos": 0, "langs": []})
                response.raise_for_status()
                sid = response.json()["session_id"]
                if not re.fullmatch(r"m-[0-9a-f]{8}", sid):
                    sid = None
                    raise ValueError("Refusing to control an unexpected or shared session identity")
                pause = await control("pause")
                if pause.get("paused") is not True:
                    raise ValueError("New isolated match did not pause")
                response = await client.get(f"{base}/api/matches/{sid}/dataset.jsonl")
                response.raise_for_status()
                if len(response.content) > 25_000_000:
                    raise ValueError("Source dataset exceeds experiment bound")
                dataset_sha = hashlib.sha256(response.content).hexdigest()
                meta, events = source_dataset(response.text, args.seed)
                response = await client.get(f"{base}/api/matches/{sid}")
                response.raise_for_status()
                initial_state = response.json()["state"]
                if initial_state.get("minute", 0) > 3:
                    raise ValueError("Startup advanced beyond the bounded replay accounting window")
                response = await client.get(f"{base}/api/matches/{sid}/window", params={"start": 0, "end": 180})
                response.raise_for_status()
                before_pause = {e["id"] for e in response.json()["events"]}
                if len(before_pause) > 20 or not before_pause <= {e["id"] for e in events}:
                    raise ValueError("Startup cannot be fully accounted for by the source dataset and 20-event replay")
                ready = [asyncio.Event() for _ in observations]
                tasks = [asyncio.create_task(receive(client, base, sid, meta["match_id"], o, signal, started))
                         for o, signal in zip(observations, ready)]
                try:
                    await asyncio.wait_for(asyncio.gather(*(signal.wait() for signal in ready)), timeout=30)
                except asyncio.TimeoutError:
                    for o, signal, task in zip(observations, ready, tasks):
                        if not signal.is_set():
                            o.error = "hello_timeout"
                            task.cancel()
                if not any(o.hello for o in observations):
                    raise ValueError("No client established an SSE connection")
                await control("speed", args.speed)
                await control("resume")
                print(f"Isolated session {sid}: {sum(o.hello for o in observations)}/{args.clients} connected; "
                      f"{len(events)} source events; {len(before_pause)} startup events retained in denominator.", flush=True)
                await asyncio.gather(*tasks, return_exceptions=True)
                response = await client.get(f"{base}/api/matches/{sid}")
                response.raise_for_status()
                final_state = response.json()["state"]
        except Exception as exc:
            error = type(exc).__name__
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if sid and not all(o.done for o in observations):
                # There is no generic-session delete API. Finish only this created match;
                # do not leave an indefinitely paused slot, or change demo/live controls.
                cleanup = await finish_isolated(control)
        report = summarize(events, observations, before_pause)
        report.update({"schema": "touchline.cloud-soak/1", "provenance": provenance(), "target": base,
                       "deployment_reference": args.deployment_ref,
                       "deployment_reference_scope": "Operator-supplied label; the runner does not infer the server's commit from its own checkout.",
                       "session": sid, "match_id": meta.get("match_id"), "seed": args.seed, "speed": args.speed,
                       "elapsed_seconds": round(time.perf_counter() - started, 2), "maximum_seconds": args.timeout_seconds,
                       "error": error, "cleanup": cleanup, "server_final_state": final_state,
                       "startup": {"speed": .5, "paused_before_subscribing": bool(initial_state.get("paused")),
                                   "already_applied_ids": sorted(before_pause), "replay_capacity": 20,
                                   "scope": "All planned source events remain in completeness denominator, including startup replay; no end-of-run exclusion."},
                       "source_dataset_sha256": dataset_sha if events else None,
                       "source_ids": [e["id"] for e in events],
                       "downstream_scope": "This isolated synthetic match uses the normal outbound pipeline; verified insights and a final synthetic match package may be delivered to configured downstream consumers. This runner does not verify their delivery.",
                       "scope": "One bounded synthetic match; clients run on one external observer machine against one deployment. Not an SLA, maximum capacity, multi-replica, reconnect or real-match test. No server-to-client latency is claimed."})
        report["passed"] = bool(report["passed"] and not error and final_state.get("status") == "full_time"
                                and final_state.get("score") == report["expected_final_score"])
        return report


def markdown(report: dict) -> str:
    spread = report["fanout_receipt_spread"]
    rows = "\n".join(f"| {c['client']} | {c['connected']} | {c['received_source_events']}/{c['expected']} | "
                     f"{len(c['missing_ids'])} | {c['score_matches']} | {c['error'] or 'none'} |" for c in report["clients"])
    return f"""# Bounded external cloud streaming experiment

Result: **{'PASSED' if report['passed'] else 'FAILED'}**. {report['clients_passed']} of {report['clients_attempted']}
attempted clients met every gate. Elapsed: {report['elapsed_seconds']} seconds; seed {report['seed']}, {report['speed']}× playback.

Target: {report['target']}. Session: `{report['session']}`. Operator deployment reference: `{report['deployment_reference']}`.
The complete server dataset contained **{report['source_event_count']} events**; expected final score: `{report['expected_final_score']}`.
{len(report['all_clients_lost_ids'])} source events were missed by every client. Failed connections stay in the denominator.
Startup events are included via the normal recent-event replay; none are silently removed from completeness.

| Client | Connected | Source events received | Missing | Final score correct | Error |
|---|---|---|---|---|---|
{rows}

For {spread['events_observed_by_every_client']} of {spread['eligible_source_events']} eligible post-start source events received by
every attempted client, receipt spread was p50 **{spread['p50_ms']} ms**, p95 **{spread['p95_ms']} ms**, max **{spread['max_ms']} ms**.
This is the gap between earliest and latest client receipt on one observer machine. It is **not end-to-end latency**.
Startup replay events are excluded only from this spread statistic, never from completeness.

{report['scope']}
Run error: `{report['error']}`. Cleanup: {report['cleanup']}.
The accompanying JSON retains every client's missing IDs, unexpected IDs, order and arrival timestamps plus source hashes.
No public model calls or shared `demo`/`live` controls are used. Only the new isolated match is created and controlled.
The match uses the normal outbound pipeline: synthetic insights and its final synthetic package may be delivered to
configured downstream consumers. Downstream delivery is not verified by this streaming experiment.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--clients", type=int, default=12)
    parser.add_argument("--speed", type=float, default=30)
    parser.add_argument("--seed", type=int, default=221)
    parser.add_argument("--timeout-seconds", type=int, default=480)
    parser.add_argument("--deployment-ref", default="not supplied")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/cloud-soak.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs/CLOUD_SOAK.md")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment
            or url.path not in ("", "/")):
        parser.error("Use an HTTP(S) deployment origin without credentials, query or path")
    if not 10 <= args.clients <= 20 or not 20 <= args.speed <= 30 or not 180 <= args.timeout_seconds <= 600:
        parser.error("Bounds: 10–20 clients, 20–30× speed, 180–600 seconds")
    if not 0 <= args.seed <= 10_000_000:
        parser.error("Seed must be between 0 and 10000000")
    report = asyncio.run(experiment(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "clients_attempted", "clients_passed", "source_event_count", "elapsed_seconds", "error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
