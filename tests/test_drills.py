"""Resilience drills: each fault is detected by the right agent and the pipeline recovers."""
import asyncio

from touchline.runtime import MatchSession


def run_with(drills, at_seq=200):
    async def go():
        s = MatchSession(seed=221, speed=1000)
        s.start()
        fired = False
        while not s.done:
            if not fired and len(s.events) > at_seq:
                for d in drills:
                    s.start_drill(d)
                fired = True
            await asyncio.sleep(0.005)
        return s
    return asyncio.run(go())


def test_all_drills_detected_and_recovered():
    s = run_with(["feed_storm", "narrator_crash", "storyline_crash", "hallucination", "llm_outage"])
    by = {d["name"]: d for d in s.drills}
    assert set(by) == set(MatchSession.DRILLS)
    assert by["feed_storm"]["detected_by"] == "IngestGuard"
    assert by["narrator_crash"]["detected_by"] == "Narrator[analyst]"
    assert by["storyline_crash"]["detected_by"] == "StorylineKeeper"
    assert by["hallucination"]["detected_by"] == "FactChecker" and "99" in by["hallucination"]["notes"][0]
    for name in ("feed_storm", "narrator_crash", "storyline_crash", "hallucination"):
        assert by[name]["recovered"], name
    # nothing fabricated aired, and no event was applied twice
    assert not any("99th" in l["text"] for i in s.insights for p in i.get("renders", {}).values() for r in p.values() for l in r["lines"])
    assert s.guard.stats["accepted"] == len(s.events)
    # the crashed narrator's moments still aired with stand-in copy
    assert any(r.get("source") == "fallback:studio" for i in s.insights for r in i.get("renders", {}).get("analyst", {}).values())


def test_fact_checker_catches_ordinals_and_shared_surnames():
    s = run_with([], at_seq=10**9)
    ins = next(i for i in s.insights if i["kind"] == "goal")
    title = ins["renders"]["casual"]["en"]["title"]
    issues = s.checker.check_text(ins, [title + ", his 99th goal of the season"])
    assert any("99" in i for i in issues)
    assert not s.checker.check_text(ins, [title])


def test_checker_binds_rewrites_and_catches_superlatives():
    s = run_with([], at_seq=10**9)
    ins = next(i for i in s.insights if i["kind"] == "goal")
    r = ins["renders"]["casual"]["en"]
    base = [r["title"]] + [l["text"] for l in r["lines"]]
    assert not s.checker.check_text(ins, base) and not s.checker.check_rewrite(base, base)
    assert s.checker.check_text(ins, [r["title"] + ", the best goal of the season"])
    line = next((t for t in base if any(ch.isdigit() for ch in t)), None)
    if line:
        import re
        n = re.search(r"\d+", line).group(0)
        assert s.checker.check_rewrite([line], [line.replace(n, str(int(n) + 1), 1)])
