"""Verify a deployed app and an actual hosted Foundry answer; health alone is not proof.

    python scripts/smoke_deployment.py https://your-app.example

Makes one normal analyst request (model usage is billed to the deployment). Does not
change playback, run drills or provision resources. Exits nonzero on fallback/failure.
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def check(base_url, expected_match=None):
    def request(path, data=None):
        req = Request(base_url.rstrip("/") + path,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=45) as response:
            return json.load(response)

    before = request("/api/health")
    if before.get("status", "ok") != "ok":
        raise RuntimeError("The app reports degraded health; check the input feed.")
    if before["llm"]["backend"] != "foundry":
        raise RuntimeError("Foundry is not configured; health status alone is insufficient.")
    match = request("/api/matches/demo")
    if not match["state"]:
        raise RuntimeError("The demo has no match state.")
    answer = request("/api/matches/demo/ask", {"question": "What is the current score? Use the scoreboard tool."})
    after = request("/api/health")
    execution = answer.get("execution", {})
    if (answer.get("source") != "llm:foundry" or execution.get("path") != "foundry_hosted"
            or not execution.get("completed") or execution.get("fallback")
            or not answer.get("grounding", {}).get("tool_results")):
        raise RuntimeError("The request did not return a verified hosted Foundry answer.")
    # Aggregate counters may change because of other viewers; the proof belongs to this request.
    downstream = None
    if expected_match:
        downstream = request("/api/downstream")
        packages = downstream.get("packages") or {}
        if (packages.get("latest") or {}).get("match_id") != expected_match or not packages.get("packages_built"):
            raise RuntimeError("The expected completed match has not reached the Functions/Blob package output.")
    return {"passed": True, "observed_at": datetime.now(timezone.utc).isoformat(),
            "url": base_url, "model": execution.get("model") or after["llm"]["model"], "answer": answer,
            "downstream": downstream,
            "scope": "One live hosted analyst request; not a load, durability or availability test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="The deployed HTTPS app URL")
    parser.add_argument("--match-id", help="Also require this completed match in the downstream Functions/Blob output")
    parser.add_argument("--output", type=Path, help="Save the observed cloud evidence as JSON")
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        parser.error("Use the deployed HTTPS URL")
    try:
        result = json.dumps(check(args.url, args.match_id), indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result, encoding="utf-8")
        print(result)
    except Exception as exc:
        print(f"Deployment check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
