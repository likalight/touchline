"""Publish Touchline's agents to Microsoft Foundry Agent Service (run by `azd up` as a postprovision hook).

    FOUNDRY_PROJECT_ENDPOINT=... FOUNDRY_MODEL=gpt-4.1-mini python scripts/foundry_publish.py

Each run creates a new version of every agent, tagged with the git commit, with the project's
Responsible-AI content policy attached. Prints the versions as JSON.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TOUCHLINE_LLM", "off")

from touchline.foundry_agents import publish  # noqa: E402


def main() -> int:
    endpoint, model = os.getenv("FOUNDRY_PROJECT_ENDPOINT"), os.getenv("FOUNDRY_MODEL")
    if not endpoint or not model:
        print("FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL are required; agent publication failed.", file=sys.stderr)
        return 1
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        sha = ""
    out = publish(endpoint, model, os.getenv("FOUNDRY_RAI_POLICY", "Microsoft.DefaultV2"), sha)
    if len(out) != 2 or any(not agent.get("version") for agent in out):
        print("Agent publication did not return both version IDs.", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
