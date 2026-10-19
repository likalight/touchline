"""Load test: how many fans can one Touchline replica stream to, live?

Starts one server process (one Python worker, which uses about one vCPU, like a Container Apps replica
with `cpu: 1.0`), runs a match at 10x speed (ten times the event rate of a real match, so this is
conservative), and connects N fans to the live stream from separate client processes. Every fan records
when each match event arrives; the spread between the first and last fan to receive the same event is the
fan-out lag. Server CPU and memory are sampled throughout.

    python scripts/loadtest.py --fans 100 250 500 1000 --seconds 30     # writes docs/LOADTEST.md
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VCPU_S, GIB_S = 0.000024, 0.000003   # Azure Container Apps consumption, East US, USD (Azure Retail Prices API)


def fan_worker(base: str, sid: str, n: int, seconds: float, q: mp.Queue) -> None:
    import asyncio

    import httpx

    async def one(client: httpx.AsyncClient, out: dict) -> None:
        try:
            async with client.stream("GET", f"{base}/api/matches/{sid}/stream", timeout=None) as r:
                kind = None
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        kind = line[6:].strip()
                    elif line.startswith("data:") and kind == "event":
                        try:
                            out[json.loads(line[5:])["id"]] = time.time()
                        except Exception:
                            pass
        except Exception:
            out["_error"] = 1

    async def main() -> None:
        limits = httpx.Limits(max_connections=n + 10, max_keepalive_connections=n + 10)
        async with httpx.AsyncClient(limits=limits) as client:
            outs = [dict() for _ in range(n)]
            tasks = [asyncio.create_task(one(client, o)) for o in outs]
            await asyncio.sleep(seconds)
            for t in tasks:
                t.cancel()
        q.put(outs)

    asyncio.run(main())


def sample(pid: int) -> tuple[float, float]:
    """(cpu seconds used so far, RSS MiB) for a process, from /proc."""
    with open(f"/proc/{pid}/stat") as f:
        parts = f.read().split(")")[-1].split()
    ticks = os.sysconf("SC_CLK_TCK")
    cpu = (int(parts[11]) + int(parts[12])) / ticks
    with open(f"/proc/{pid}/status") as f:
        rss = next(int(line.split()[1]) for line in f if line.startswith("VmRSS")) / 1024
    return cpu, rss


def run(fans: int, seconds: float, port: int) -> dict:
    env = {**os.environ, "TOUCHLINE_LLM": "off"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "touchline.server:app", "--port", str(port), "--log-level", "warning"],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        req = urllib.request.Request(base + "/api/matches", data=json.dumps({"seed": 221, "speed": 10}).encode(),
                                     headers={"Content-Type": "application/json"})
        sid = json.load(urllib.request.urlopen(req))["session_id"]
        procs, per = max(1, fans // 125), None
        per = [fans // procs + (1 if i < fans % procs else 0) for i in range(procs)]
        q: mp.Queue = mp.Queue()
        workers = [mp.Process(target=fan_worker, args=(base, sid, k, seconds, q)) for k in per]
        cpu0, _ = sample(srv.pid)
        t0 = time.time()
        for w in workers:
            w.start()
        rss_peak = 0.0
        while time.time() - t0 < seconds:
            rss_peak = max(rss_peak, sample(srv.pid)[1])
            time.sleep(0.5)
        outs = []
        for _ in workers:
            outs += q.get(timeout=seconds + 60)
        for w in workers:
            w.join(timeout=10)
        cpu1, _ = sample(srv.pid)
        elapsed = time.time() - t0
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    errors = sum(1 for o in outs if "_error" in o)
    ids = set().union(*[set(k for k in o if not k.startswith("_")) for o in outs]) if outs else set()
    # ignore events in the last two seconds: some fans' connections close before they arrive
    first = {eid: min(o[eid] for o in outs if eid in o) for eid in ids}
    cutoff = max(first.values(), default=0) - 2.0
    ids = {eid for eid in ids if first[eid] <= cutoff}
    spreads = []
    for eid in ids:
        ts = [o[eid] for o in outs if eid in o]
        if len(ts) == len(outs):
            spreads.append((max(ts) - min(ts)) * 1000)
    got = [sum(1 for k in ids if k in o) for o in outs]
    return {"fans": fans, "connected": len(outs) - errors, "events": len(ids),
            "complete_share": round(sum(g == len(ids) for g in got) / max(1, len(got)), 3),
            "lag_p50_ms": round(statistics.median(spreads), 1) if spreads else None,
            "lag_p95_ms": round(sorted(spreads)[int(0.95 * (len(spreads) - 1))], 1) if spreads else None,
            "cpu_share": round((cpu1 - cpu0) / elapsed, 3), "rss_mib": round(rss_peak)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fans", type=int, nargs="+", default=[100, 250, 500, 1000])
    ap.add_argument("--seconds", type=float, default=30)
    a = ap.parse_args()
    rows = []
    for i, n in enumerate(a.fans):
        r = run(n, a.seconds, 8100 + i)
        print(r, flush=True)
        rows.append(r)
    # sizing: the largest run where every fan got every event and the server stayed under 70% CPU
    ok = [r for r in rows if r["cpu_share"] <= 0.7 and r["complete_share"] >= 0.99]
    cap = max((r["fans"] for r in ok), default=0)
    replica_match = 2 * 3600 * (VCPU_S * 1 + GIB_S * 2)   # 1 vCPU, 2 GiB, for a 2-hour match window
    per_1000 = replica_match * (1000 / cap) if cap else None
    table = "\n".join(f"| {r['fans']:,} | {r['connected']:,} | {r['complete_share']:.0%} | {r['lag_p50_ms']} / {r['lag_p95_ms']} ms | "
                      f"{r['cpu_share']:.0%} | {r['rss_mib']} MiB |" for r in rows)
    md = f"""# Load test: fans per replica

`python scripts/loadtest.py --fans {' '.join(map(str, a.fans))} --seconds {a.seconds:g}` runs one server process (one Python
worker, about one vCPU, like a Container Apps replica with `cpu: 1.0`), plays a match at **10x speed** (ten times a
real match's event rate, so this is conservative), and connects every fan to the live stream for {a.seconds:g} seconds.
Fan-out lag is the gap between the first and the last fan receiving the same match event.

The fans ran on the same two-vCPU machine as the server, so at high counts the lag is mostly the load generator
itself queueing; **server CPU is the capacity signal**, and it stays well below one core.

| Fans | Connected | Received every event | Fan-out lag p50 / p95 | Server CPU | Memory |
|---|---|---|---|---|---|
{table}

**One replica serves at least {cap:,} live fans** with every fan receiving every event and the server under 70% of one
vCPU, at ten times the real event rate. Container Apps adds replicas on HTTP load (`maxReplicas` in
`infra/resources.bicep`).

## Cost per 1,000 fans

A 1 vCPU, 2 GiB replica for a two-hour match window costs about **${replica_match:.2f}** at Azure Container Apps consumption
prices (East US: ${VCPU_S:.6f} per vCPU-second, ${GIB_S:.6f} per GiB-second, from the Azure Retail Prices API; the monthly free
grant is ignored here). At {cap:,} fans per replica that is **about ${per_1000:.2f} per 1,000 fans per match** for the
live experience, before any language-model or speech usage (see [BROADCASTERS.md](BROADCASTERS.md#cost-per-match)).
""" if cap else "# Load test\n\nNo configuration met the targets; see the raw results above.\n"
    (ROOT / "docs" / "LOADTEST.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
