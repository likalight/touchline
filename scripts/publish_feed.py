"""Publish a synthetic match onto Azure Event Hubs in real time (event-driven demo).

    export TOUCHLINE_EVENTHUB_NAMESPACE=<ns>.servicebus.windows.net   # managed identity / az login
    python scripts/publish_feed.py --seed 42 --speed 10

The deployed app consumes the hub and serves the match as session `live`:
open <app-url>/?session=live
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from touchline.feeds import publish_match  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--speed", type=float, default=10.0, help="x real time")
    a = ap.parse_args()
    n = asyncio.run(publish_match(a.seed, a.speed))
    print(f"published {n} events")
