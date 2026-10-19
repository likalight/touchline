"""What if? Counterfactual replays of the rest of a match.

Pick a moment ("Calloway is not sent off", "Mbeki's goal is ruled out"), and Touchline rebuilds the match
state at that minute, applies the change, and replays the remaining minutes 1,000 times with the same
goal model that drives the live win probability (expected goals per minute from the match so far, adjusted
for players sent off and stoppage time). It compares the outcome with the same replays without the change
and with what actually happened.

These are model estimates, clearly labelled as such; the match facts they start from are the verified state.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from touchline.analytics.state import MatchState

N_REPLAYS = 1000


def state_at(session, minute: float) -> MatchState:
    """The match state just before `minute` (events strictly earlier), rebuilt from the verified feed."""
    st = MatchState(session.meta)
    for ev in session.events:
        if ev.t >= minute * 60 or ev.id not in session.state.enriched:
            break
        st.apply(ev)
    return st


def scenarios(session) -> list[dict]:
    """Suggested what-ifs from the match itself: every goal and every red card so far."""
    out, names = [], {pid: p.name for pid, p in session.state.players.items()}
    teams = {"home": session.meta.home.name, "away": session.meta.away.name}
    for ev in session.events:
        if ev.id not in session.state.enriched:
            break
        who = names.get(ev.player_id, teams.get(ev.team or "", ""))
        if ev.type == "goal" and ev.team:
            out.append({"id": f"nogoal:{ev.id}", "kind": "remove_goal", "event_id": ev.id, "team": ev.team, "minute": ev.minute,
                        "label": f"{who}'s {ev.minute}' goal is ruled out"})
        if ev.type == "card" and ev.outcome in ("red", "second_yellow") and ev.team:
            out.append({"id": f"nored:{ev.id}", "kind": "remove_red", "event_id": ev.id, "team": ev.team, "minute": ev.minute,
                        "label": f"{who} is not sent off ({ev.minute}')"})
    m = max(1, session.state.minute)
    for side in ("home", "away"):
        out.append({"id": f"goal:{side}:{min(m, 60)}", "kind": "add_goal", "team": side, "minute": min(m, 60),
                    "label": f"{teams[side]} score in minute {min(m, 60)}"})
    return out


def _replay(st: MatchState, score: dict, reds: dict, rng: np.random.Generator, n: int) -> dict:
    saved = dict(st.reds)
    st.reds.update(reds)
    lam_h, lam_a = st.remaining_lambda()
    st.reds.update(saved)
    gh = rng.poisson(lam_h, n) + score["home"]
    ga = rng.poisson(lam_a, n) + score["away"]
    res = {"home": float(np.mean(gh > ga)), "draw": float(np.mean(gh == ga)), "away": float(np.mean(gh < ga))}
    pairs, counts = np.unique(np.stack([gh, ga], 1), axis=0, return_counts=True)
    top = sorted(zip(pairs.tolist(), counts.tolist()), key=lambda x: -x[1])[:3]
    return {"result": {k: round(v, 3) for k, v in res.items()}, "lambda": {"home": round(lam_h, 2), "away": round(lam_a, 2)},
            "scorelines": [{"home": int(p[0]), "away": int(p[1]), "share": round(c / n, 3)} for p, c in top]}


def run(session, scenario_id: str, n: int = N_REPLAYS, seed: int = 7) -> Optional[dict]:
    sc = next((s for s in scenarios(session) if s["id"] == scenario_id), None)
    if sc is None:
        return None
    minute = sc["minute"]
    # for a goal or a card, start the replay just after that event, so both branches share everything before it
    ev = next((e for e in session.events if e.id == sc.get("event_id")), None)
    st = state_at(session, (ev.t + 0.5) / 60 if ev else minute)
    rng = np.random.default_rng(seed)
    score, reds = dict(st.score), dict(st.reds)
    base = _replay(st, score, reds, rng, n)
    side, other = sc["team"], "away" if sc["team"] == "home" else "home"
    if sc["kind"] == "remove_goal":
        score[side] = max(0, score[side] - 1)
    elif sc["kind"] == "remove_red":
        reds[side] = max(0, reds[side] - 1)
    elif sc["kind"] == "add_goal":
        score[side] += 1
    changed = _replay(st, score, reds, np.random.default_rng(seed), n)
    teams = {"home": session.meta.home.name, "away": session.meta.away.name}
    final = dict(session.state.score)

    def word(r: str) -> str:
        return {"home": f"{teams['home']} win", "away": f"{teams['away']} win", "draw": "a draw"}[r]

    best = max(changed["result"], key=changed["result"].get)
    d = changed["result"][side] - base["result"][side]
    summary = (f"From minute {minute}, {teams[side]} win {changed['result'][side]:.0%} of {n:,} replays with the change, "
               f"against {base['result'][side]:.0%} without it ({'+' if d >= 0 else ''}{d * 100:.0f} points). "
               f"The likeliest outcome is {word(best)}.")
    summary += (f" What actually happened: {teams['home']} {final['home']}-{final['away']} {teams['away']}."
                if session.done else " The match is still being played.")
    return {"scenario": sc, "from_minute": minute, "replays": n, "as_it_was": base, "what_if": changed,
            "actual_final": final, "finished": session.done, "summary": summary,
            "note": "Model estimate: remaining goals drawn from each side's expected-goal rate so far, adjusted for red cards and stoppage time."}
