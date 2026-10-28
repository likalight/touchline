"""One bounded, external snapshot-resynchronization probe; no lossless replay claim.

Creates one private accelerated simulation, disconnects for more than 20 events,
checks source-derived current score and recent event order on reconnect, then
checks a completed-match reconnect. No LLM calls or shared-match mutations.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evidence_provenance import provenance
from scripts.cloud_soak import source_dataset


async def bootstrap(client, sid, *, terminal=False, initial=False):
    async with asyncio.timeout(30):
        return await _bootstrap(client, sid, terminal=terminal, initial=initial)


async def _bootstrap(client, sid, *, terminal=False, initial=False):
    messages = []
    async with client.stream("GET", f"/api/matches/{sid}/stream") as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            message = json.loads(line[6:])
            messages.append(message)
            if initial and message["type"] == "state":
                break
            if terminal and message["type"] == "done":
                break
            if not terminal and not initial and sum(m["type"] == "event" for m in messages) == 20:
                break
    return messages


async def run(base):
    async with httpx.AsyncClient(base_url=base, timeout=25) as client:
        async def get(path):
            response = await client.get(path)
            response.raise_for_status()
            return response.json()

        response = await client.post("/api/matches", json={"seed": 221, "speed": 240})
        response.raise_for_status()
        sid = response.json()["session_id"]
        if not re.fullmatch(r"m-[a-f0-9]{8}", sid):
            raise AssertionError("Refusing to control a non-private session")

        async def control(action):
            response = await client.post(f"/api/matches/{sid}/control", json={"action": action})
            response.raise_for_status()

        await control("pause")
        await asyncio.sleep(.5)
        source = await client.get(f"/api/matches/{sid}/dataset.jsonl")
        source.raise_for_status()
        _, events = source_dataset(source.text, 221)
        initial = await bootstrap(client, sid, initial=True)
        initial_count = next(m for m in initial if m["type"] == "state")["ops"]["applied_events"]
        await control("resume")
        deadline = time.monotonic() + 90
        while (await get(f"/api/matches/{sid}"))["state"]["minute"] < 25:
            if time.monotonic() > deadline:
                raise AssertionError("Private simulation did not advance within bounded deadline")
            await asyncio.sleep(.5)
        await control("pause")
        await asyncio.sleep(.5)
        current = await get(f"/api/matches/{sid}")
        recovered = await bootstrap(client, sid)
        hello = recovered[0]
        state = next(m for m in recovered if m["type"] == "state")
        recent = [m for m in recovered if m["type"] == "event"]
        last_seq = recent[-1]["seq"]
        applied = state["ops"]["applied_events"]
        expected_ids = [e["id"] for e in events[applied - 20:applied]]
        expected_score = {side: sum(e["type"] == "goal" and e.get("team") == side for e in events[:applied])
                          for side in ("home", "away")}
        checks = {
            "explicit_snapshot_contract": hello["recovery"]["mode"] == "snapshot" and hello["recovery"]["lossless_event_replay"] is False,
            "gap_exceeds_history": recent[0]["seq"] > initial_count + 1,
            "recent_source_order": [e["id"] for e in recent] == expected_ids,
            "history_reaches_applied_state": last_seq == applied == current["state"]["ops"]["applied_events"],
            "history_flagged_replayed": all(e.get("replayed") is True for e in recent),
            "score_matches_source": state["score"] == expected_score,
            "snapshot_matches_paused_http": all(state[k] == current["state"][k] for k in ("match_id", "minute", "score", "players", "paused", "timeline")),
        }
        await control("resume")
        while not (await get(f"/api/matches/{sid}"))["done"]:
            if time.monotonic() > deadline:
                raise AssertionError("Private simulation did not finish within bounded deadline")
            await asyncio.sleep(1)
        completed = await bootstrap(client, sid, terminal=True)
        final_state = next(m for m in completed if m["type"] == "state")
        final_score = {side: sum(e["type"] == "goal" and e.get("team") == side for e in events)
                       for side in ("home", "away")}
        checks.update(completed_hello=completed[0]["done"] is True,
                      completed_state=final_state["status"] == "full_time" and final_state["score"] == final_score,
                      completed_signal=completed[-1] == {"type": "done", "replayed": True})
        return {"schema": "touchline.reconnect-probe/1", "base_url": base, "provenance": provenance(),
                "session": sid, "seed": 221, "speed": 240, "passed": all(checks.values()), "checks": checks,
                "initial_applied_events": initial_count, "reconnected_last_seq": last_seq,
                "unreplayed_gap_events": recent[0]["seq"] - initial_count - 1,
                "recovered_event_ids": [e["id"] for e in recent], "expected_recent_ids": expected_ids,
                "reconnected_score": state["score"], "expected_reconnected_score": expected_score,
                "final_score": final_state["score"], "expected_final_score": final_score,
                "scope": "One deliberately disconnected client, one private accelerated synthetic match. Snapshot and bounded history recovery, not lossless event replay, capacity or availability proof. The private session expires after 15 minutes."}


async def bounded_run(base):
    async with asyncio.timeout(150):
        return await run(base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(bounded_run(args.base_url.rstrip("/")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "checks": result["checks"], "output": str(args.output)}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
