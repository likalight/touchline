"""Verify a deployed app and an actual hosted Foundry answer; health alone is not proof.

    python scripts/smoke_deployment.py https://your-app.example

Makes one normal analyst request (model usage is billed to the deployment). Does not
change playback, run drills or provision resources. Exits nonzero on fallback/failure.
"""
import argparse
import json
import sys
from urllib.request import Request, urlopen


def check(base_url):
    def request(path, data=None):
        req = Request(base_url.rstrip("/") + path,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=45) as response:
            return json.load(response)

    before = request("/api/health")
    if before["llm"]["backend"] != "foundry":
        raise RuntimeError("Foundry is not configured; health status alone is insufficient.")
    match = request("/api/matches/demo")
    if not match["state"]:
        raise RuntimeError("The demo has no match state.")
    answer = request("/api/matches/demo/ask", {"question": "What is the current score? Use the scoreboard tool."})
    after = request("/api/health")
    if answer.get("source") != "llm:foundry" or "AskTheAnalyst" not in after["llm"]["hosted_agents"]:
        raise RuntimeError("The request did not return a verified hosted Foundry answer.")
    if after["llm"]["hosted_fallbacks"] != before["llm"]["hosted_fallbacks"]:
        raise RuntimeError("A hosted-agent fallback occurred during the check.")
    return {"passed": True, "model": after["llm"]["model"], "answer": answer,
            "scope": "One live hosted analyst request; not a load, durability or availability test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="The deployed HTTPS app URL")
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        parser.error("Use the deployed HTTPS URL")
    try:
        print(json.dumps(check(args.url), indent=2))
    except Exception as exc:
        print(f"Deployment check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
