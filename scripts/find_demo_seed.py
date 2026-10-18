"""Search the synthetic league for the most watchable match to demo.

Drama score rewards what makes a match a story: a comeback, a late winner, several
lead changes, big win-probability swings, a red card, a hat-trick, an upset against
the run of chances. Prints the top seeds.

    python scripts/find_demo_seed.py --seeds 400
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from touchline.analytics.state import MatchState  # noqa: E402
from touchline.sim.engine import simulate  # noqa: E402


def drama(seed: int) -> dict:
    meta, evs = simulate(seed)
    s = MatchState(meta)
    swings, leader_changes, trailed, last_goal_min = [], 0, {"home": False, "away": False}, 0
    lead = None
    scorers: dict = {}
    for e in evs:
        en = s.apply(e)
        if e.type == "goal":
            last_goal_min = e.minute
            scorers[e.player_id] = scorers.get(e.player_id, 0) + 1
            h, a = s.score["home"], s.score["away"]
            new = "home" if h > a else "away" if a > h else None
            if new != lead and new is not None and lead is not None:
                leader_changes += 1
            lead = new
            if h < a:
                trailed["home"] = True
            if a < h:
                trailed["away"] = True
        if en.wp_before and e.team:
            swings.append(abs(en.wp_after[e.team] - en.wp_before[e.team]))
    h, a = s.score["home"], s.score["away"]
    winner = "home" if h > a else "away" if a > h else None
    goals = h + a
    xg = {k: s.team[k]["xg"] for k in ("home", "away")}
    score = 0.0
    score += min(goals, 6) * 0.6 - max(0, goals - 6) * 0.8
    score += 2.5 if winner and trailed[winner] else 0
    score += 2.0 if winner and last_goal_min >= 80 and abs(h - a) == 1 else 0
    score += leader_changes * 1.2
    score += 1.5 if s.reds["home"] + s.reds["away"] else 0
    score += 1.5 if max(scorers.values(), default=0) >= 3 else 0.6 if max(scorers.values(), default=0) == 2 else 0
    score += 1.0 if winner and xg[winner] < xg["away" if winner == "home" else "home"] else 0
    score += sum(sorted(swings)[-3:]) * 3
    score -= 3 if goals == 0 else 0
    return {"seed": seed, "score": round(score, 2), "final": f"{h}-{a}", "goals": goals, "comeback": bool(winner and trailed[winner]),
            "late_winner_min": last_goal_min if winner and abs(h - a) == 1 and last_goal_min >= 80 else None,
            "lead_changes": leader_changes, "reds": s.reds["home"] + s.reds["away"], "max_by_one_player": max(scorers.values(), default=0),
            "xg": {k: round(v, 2) for k, v in xg.items()}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=400)
    a = ap.parse_args()
    rows = sorted((drama(sd) for sd in range(a.seeds)), key=lambda r: -r["score"])
    for r in rows[:12]:
        print(r)
