"""Evaluation harness and CI gate.

Runs N full synthetic matches (optionally with a faulty feed) through the complete agent
pipeline and measures what a broadcaster would care about:

* groundedness  - share of insights the FactChecker verified; every citation resolves to a
                  real, non-future event
* coverage      - moments explained per match, kinds covered, goals explained (must be 100%)
* personalisation - personas x languages rendered without template leaks
* latency       - per-event state update and per-moment agent pipeline, p50 / p95
* resilience    - events recovered exactly-once from a 10% faulty feed

    python scripts/evaluate.py --matches 20 --gate          # fails (exit 1) if any threshold is missed
    python scripts/evaluate.py --foundry                    # + Azure AI Foundry groundedness evaluator (needs env)

Writes docs/EVAL.md.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TOUCHLINE_LLM", "off")

from touchline.agents.narrator import PERSONAS  # noqa: E402
from touchline.i18n import BANKS  # noqa: E402
from touchline.runtime import MatchSession, percentile  # noqa: E402
from scripts.evidence_provenance import provenance  # noqa: E402

GATES = {
    "verified_rate": 1.0, "goals_explained": 1.0, "template_leaks": 0, "citation_errors": 0,
    "pipeline_ms_p95": 250.0, "event_ms_p95": 5.0, "exactly_once": 1.0,
}


async def run(seed: int, chaos: float) -> MatchSession:
    s = MatchSession(seed=seed, speed=1000, chaos=chaos)
    s.control("jump", 200)
    s.start()
    while not s.done:
        await asyncio.sleep(0.02)
    return s


def foundry_groundedness(samples: list[dict]) -> dict | None:
    """Optional: score rendered copy against its evidence with azure-ai-evaluation."""
    try:
        from azure.ai.evaluation import GroundednessEvaluator
    except Exception:
        return None
    cfg = {"azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"), "azure_deployment": os.getenv("AZURE_OPENAI_MODEL"),
           "api_key": os.getenv("AZURE_OPENAI_API_KEY")}
    if not all(cfg.values()):
        return None
    ev = GroundednessEvaluator(model_config=cfg)
    scores = []
    for s in samples[:40]:
        r = ev(response=s["text"], context=s["context"])
        scores.append(float(r.get("groundedness", 0)))
    return {"groundedness_mean_1to5": round(statistics.mean(scores), 2), "n": len(scores)}


def video_sections() -> str:
    import json

    out = ""
    p = ROOT / "docs" / "autoevent_eval.json"
    if p.exists():
        d = json.loads(p.read_text())
        pa, sh = d["passes"], d["shots"]
        out += f"""
## Auto-eventing from video (top-down feed)

`python -m touchline.vision.autoevent --seed {d['seed']} --from-min {d['window_min'][0]:g} --minutes {d['window_min'][1] - d['window_min'][0]:g}`
renders the match as a noisy {d['resolution']} feed at {d['fps']} fps ({d['frames']:,} frames). The detector sees only pixels.

| Metric | Result |
|---|---|
| Passes: precision / recall | {pa['precision']} / {pa['recall']} ({pa['matched']} of {pa['ground_truth']}) |
| Passer and receiver both identified | {round(pa['passer_and_receiver_correct'] * 100)}% |
| Ball-speed error (mean absolute) | {pa['ball_speed_mae_kmh']} km/h |
| Pass-distance error (mean absolute) | {pa['distance_mae_m']} m |
| Shots: recall | {sh['recall']} ({round(sh['recall'] * sh['ground_truth'])} of {sh['ground_truth']}) |
"""
    p = ROOT / "docs" / "broadcast_cv_eval.json"
    if p.exists():
        d = json.loads(p.read_text())
        lo, pa = d["localisation"], d["passes"]
        out += f"""
## Computer vision from the broadcast camera (experimental)

`python -m touchline.vision.broadcast_cv` renders the angled TV view ({d['resolution']}, {d['frames']:,} frames) and maps
pixels back to the pitch through the calibrated camera (pan telemetry only).

| Metric | Result |
|---|---|
| Player localisation error, p50 / p90 | **{lo['player_error_m_p50']} m / {lo['player_error_m_p90']} m** over {lo['player_detections']:,} detections |
| Ball on the ground located within 1 m | {round(lo['ball_on_ground_within_1m'] * 100)}% of frames |
| Passes detected: precision / recall (recall on passes fully in shot) | {pa['precision']} / {pa['recall']} ({pa['recall_in_shot']}) |

Player positions from the angled camera are reliable. Ball tracking from that angle (small, fast, often
airborne or occluded) is the open problem, so pass detection from the broadcast view is experimental; the
top-down detector above is the one we rely on.
"""
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=12)
    ap.add_argument("--chaos", type=float, default=0.10)
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--foundry", action="store_true")
    ap.add_argument("--json-out", type=Path, help="Save measured metrics and gates as a machine-readable evidence artifact")
    args = ap.parse_args()
    if not 1 <= args.matches <= 1000 or not 0 <= args.chaos <= 1:
        ap.error('--matches must be 1..1000 and --chaos must be 0..1')
    run_provenance = provenance()
    t0 = time.time()
    n_ins, verified, goals, goals_explained, leaks, cite_err = 0, 0, 0, 0, 0, 0
    kinds: Counter = Counter()
    callbacks: Counter = Counter()
    lat, ev_lat, per_match, exactly = [], [], [], []
    samples = []
    for i in range(args.matches):
        seed = 5000 + i
        s = asyncio.run(run(seed, args.chaos if i % 2 else 0.0))
        observed = list(s.state.events.values())
        exactly.append(int(s.guard.stats["accepted"] == len(s.events)
                           and [e.id for e in observed] == [e.id for e in s.events]
                           and all(a.seq < b.seq for a, b in zip(observed, observed[1:]))))
        goals += sum(e.type == "goal" for e in s.events)
        goals_explained += sum(1 for x in s.insights if x["kind"] == "goal")
        per_match.append(len(s.insights))
        lat += list(s.latencies)
        ev_lat += list(s.event_latency)
        callbacks.update(k for ins in s.insights for k in ins.get("storyline", []))
        for ins in s.insights:
            n_ins += 1
            kinds[ins["kind"]] += 1
            verified += ins["verification"]["status"] == "verified"
            for eid in ins["event_ids"]:
                e = s.state.events.get(eid)
                if e is None or e.t > ins["t"] + 1:
                    cite_err += 1
            for p in PERSONAS:
                for lang in BANKS:
                    r = ins["renders"][p][lang]
                    for text in [r["title"]] + [x["text"] for x in r["lines"]]:
                        if "{" in text or "@v." in text:
                            leaks += 1
            if len(samples) < 60 and ins["kind"] in ("goal", "chance_saved", "line_break", "momentum"):
                ctx = "; ".join(str(s.state.enriched[e].facts()) for e in ins["event_ids"] if e in s.state.enriched)
                r = ins["renders"]["analyst"]["en"]
                samples.append({"text": r["title"] + ". " + " ".join(x["text"] for x in r["lines"]), "context": ctx})
    m = {
        "matches": args.matches, "insights": n_ins, "insights_per_match": round(statistics.mean(per_match), 1),
        "verified_rate": round(verified / n_ins, 4) if n_ins else 0, "goals": goals,
        "goals_explained": round(goals_explained / goals, 4) if goals else 1.0, "kinds": dict(kinds.most_common()),
        "renders_per_insight": len(PERSONAS) * len(BANKS), "template_leaks": leaks, "citation_errors": cite_err,
        "pipeline_ms_p50": percentile(lat, 0.5), "pipeline_ms_p95": percentile(lat, 0.95),
        "event_ms_p50": percentile(ev_lat, 0.5), "event_ms_p95": percentile(ev_lat, 0.95),
        "exactly_once": round(statistics.mean(exactly), 3), "secs": round(time.time() - t0, 1),
    }
    if args.foundry:
        m["foundry"] = foundry_groundedness(samples) or "skipped (set AZURE_OPENAI_* and install azure-ai-evaluation)"
    fails = []
    for k, v in GATES.items():
        ok = m[k] <= v if k in ("template_leaks", "citation_errors", "pipeline_ms_p95", "event_ms_p95") else m[k] >= v
        if not ok:
            fails.append(f"{k}={m[k]} (gate {v})")
    if args.json_out:
        digest = hashlib.sha256()
        for directory in ("touchline", "scripts", "tests", "web", "infra"):
            for path in sorted((ROOT / directory).rglob("*")):
                if path.suffix in {".py", ".js", ".html", ".css", ".bicep"}:
                    digest.update(path.relative_to(ROOT).as_posix().encode())
                    digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        report = {"schema": "touchline.evaluation/1", "generated_at": datetime.now(timezone.utc).isoformat(),
                  "source_sha256": digest.hexdigest(), "provenance": run_provenance, "mode": "deterministic synthetic evaluation",
                  "seeds": list(range(5000, 5000 + args.matches)), "metrics": m, "gates": GATES,
                  "passed": not fails, "failures": fails,
                  "scope": "Local server pipeline; excludes cloud models, network delivery, speech and human usability."}
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    kinds_md = "\n".join(f"| {k} | {v} |" for k, v in m["kinds"].items())
    (ROOT / "docs" / "EVAL.md").write_text(f"""# Evaluation

`python scripts/evaluate.py --matches {args.matches} --gate` on {args.matches} unseen synthetic matches
(seeds 5000+, half of them through a {int(args.chaos * 100)}% faulty feed), deterministic path. The CI workflow runs it on every push.

Observed {run_provenance['generated_at']}. Git HEAD `{run_provenance['git_head']}`; dirty working tree: `{run_provenance['working_tree_dirty']}`.
Simulator SHA-256: `{run_provenance['simulator_sha256']}`. Frozen model artifact SHA-256: `{run_provenance['model_artifact_sha256']}`.
This reruns the pipeline with the frozen models; it does not refit or independently recalibrate them. A verified rate measures the implemented checks, not universal semantic correctness.

| Metric | Result | Gate |
|---|---|---|
| Insights verified by the FactChecker | {m['verified_rate'] * 100:.1f}% | 100% |
| Goals explained | {m['goals_explained'] * 100:.1f}% ({m['goals']} goals) | 100% |
| Citations resolving to a real, non-future event | {m['citation_errors']} errors | 0 |
| Renders per insight (4 personas x 4 languages) | {m['renders_per_insight']}, {m['template_leaks']} template leaks | 0 leaks |
| Moments explained per match | {m['insights_per_match']} | - |
| Agent pipeline latency per moment, p50 / p95 | {m['pipeline_ms_p50']} / {m['pipeline_ms_p95']} ms | p95 < 250 ms |
| Event -> state update, p50 / p95 | {m['event_ms_p50']} / {m['event_ms_p95']} ms | p95 < 5 ms |
| Faulty feed recovered exactly-once, in order | {m['exactly_once'] * 100:.0f}% of matches | 100% |
{"| Azure AI Foundry groundedness (1-5) | " + str(m["foundry"]) + " | - |" if args.foundry else ""}

Moment kinds explained across the run:

| Kind | Count |
|---|---|
{kinds_md}

Storyline callbacks woven into live insights (match-long memory): {", ".join(f"{k} {v}" for k, v in callbacks.most_common()) or "none"}.

Gate: {"PASSED" if not fails else "FAILED: " + ", ".join(fails)}. Wall time {m['secs']} s.
""" + video_sections())
    print(m)
    if fails:
        print("GATE FAILED:", fails)
        return 1 if args.gate else 0
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
