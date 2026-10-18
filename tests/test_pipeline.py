import asyncio
import copy
import re

import pytest

from touchline.agents.ingest import FaultInjector, IngestGuard
from touchline.agents.narrator import PERSONAS
from touchline.i18n import BANKS
from touchline.runtime import MatchSession
from touchline.sim.engine import simulate


async def run_session(seed=7, chaos=0.0):
    s = MatchSession(seed=seed, speed=1000, chaos=chaos)
    s.control("jump", 200)
    s.start()
    while not s.done:
        await asyncio.sleep(0.05)
    return s


@pytest.fixture(scope="module")
def session():
    return asyncio.run(run_session(7))


def test_every_insight_is_verified_and_cites_real_past_events(session):
    assert len(session.insights) >= 25
    for ins in session.insights:
        assert ins["verification"]["status"] == "verified", ins["verification"]
        for eid in ins["event_ids"]:
            ev = session.state.events[eid]
            assert ev.t <= ins["t"] + 1.0


def test_every_persona_and_language_renders_cleanly(session):
    for ins in session.insights:
        for p in PERSONAS:
            for lang in BANKS:
                r = ins["renders"][p][lang]
                assert r["title"]
                for text in [r["title"]] + [l["text"] for l in r["lines"]]:
                    assert "{" not in text and "@v." not in text, text


def test_personas_are_genuinely_different(session):
    goal = next(i for i in session.insights if i["kind"] == "goal")
    casual, analyst = goal["renders"]["casual"]["en"], goal["renders"]["analyst"]["en"]
    assert len(analyst["lines"]) > len(casual["lines"])
    assert any("xG" in l["text"] for l in analyst["lines"])
    assert not any(re.search(r"\bxG\b", l["text"]) for l in casual["lines"])
    access = goal["renders"]["access"]["en"]
    assert "speech" in access and "→" not in access["speech"]


def test_overlay_cues_follow_the_contract(session):
    cues = [i["cue"] for i in session.insights if i.get("cue")]
    assert cues
    for c in cues:
        assert c["schema"] == "touchline.overlay/1"
        assert c["out_at_t"] > c["in_at_t"] >= c["clock"]["match_t"]
        assert c["layer"] in {"lower_third", "side_panel", "player_tag", "full_screen"}


def test_latency_budget(session):
    ops = session.ops()
    assert ops["pipeline_ms_p95"] < 250  # deterministic path: well inside a broadcast frame budget
    assert ops["event_ms_p95"] < 5


def test_recap_and_ask(session):
    r = session.get_recap("analyst", "en")
    assert r["title"] and len(r["lines"]) >= 3
    ans = asyncio.run(session.ask_agent.ask("Why did they score?"))
    assert ans["answer"] and ans["citations"]


def test_ingest_guard_recovers_a_faulty_feed():
    _, evs = simulate(9)
    inj = FaultInjector(0.15, seed=1)
    g = IngestGuard(max_wait_s=30)
    out = []
    for payload in inj.apply(evs):
        out += g.push(payload)
    out += g.flush()
    assert [e.id for e in out] == [e.id for e in evs]  # exactly once, in order
    assert g.stats["quarantined"] == inj.injected["corrupt"]
    assert g.stats["duplicates"] == inj.injected["duplicate"]


def test_fact_checker_blocks_tampered_numbers(session):
    goal = copy.deepcopy(next(i for i in session.insights if i["kind"] == "goal"))
    for fr in goal["reasons"]:
        if fr["k"] == "r.chance_quality":
            fr["p"]["xg"] = round(fr["p"]["xg"] + 0.2, 2)
    assert session.checker.check_insight(goal)["status"] == "blocked"


def test_fact_checker_rejects_invented_numbers_and_players(session):
    goal = next(i for i in session.insights if i["kind"] == "goal")
    other = next(p.name for p in session.state.players.values() if p.name not in str(goal))
    issues = session.checker.check_text(goal, [f"A 97% chance, set up by {other}"])
    assert any("97" in i for i in issues) and any(other in i for i in issues)


def test_faulty_session_end_to_end():
    s = asyncio.run(run_session(21, chaos=0.1))
    assert s.guard.stats["accepted"] == len(s.events)
    assert all(i["verification"]["status"] == "verified" for i in s.insights)
