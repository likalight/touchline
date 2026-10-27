import asyncio
import copy
from pathlib import Path

import numpy as np
import pytest

from touchline.highlights import plan_reel
from touchline.runtime import MatchSession
from touchline.speech import Speech
from touchline.vision.camera import Camera


@pytest.fixture(scope="module")
def demo():
    async def go():
        s = MatchSession(seed=87, speed=1000)
        s.control("jump", 200)
        s.start()
        while not s.done:
            await asyncio.sleep(0.05)
        return s
    return asyncio.run(go())


def test_demo_match_tells_its_story(demo):
    arcs = {k for i in demo.insights for k in i.get("storyline", [])}
    assert {"s.redemption", "s.comeback", "s.error"} <= arcs
    assert all(i["verification"]["status"] == "verified" for i in demo.insights)
    rc = demo.get_recap("casual", "en")
    text = " ".join(l["text"] for l in rc["lines"])
    assert "hat-trick" in text and "90" in text


def test_story_numbers_are_recounted(demo):
    story = next(i for i in demo.insights if i["kind"] == "story_duel")
    bad = copy.deepcopy(story)
    bad["reasons"][0]["p"]["count"] += 1
    assert demo.checker.check_insight(bad)["status"] == "blocked"
    goal = next(i for i in demo.insights if "s.error" in i.get("storyline", []))
    bad = copy.deepcopy(goal)
    for f in bad["reasons"]:
        if f["k"] == "s.error":
            f["p"]["seconds"] += 5
    assert demo.checker.check_insight(bad)["status"] == "blocked"


def test_no_insight_uses_the_future(demo):
    for ins in demo.insights:
        for eid in ins["event_ids"]:
            assert demo.state.events[eid].t <= ins["t"] + 1.0


def test_personal_reel_plan(demo):
    edl = plan_reel(demo, club="home", player="h9", lang="es")
    goals = [c for c in edl["clips"] if c["kind"] == "goal"]
    assert len(goals) == demo.state.score["home"] + demo.state.score["away"]
    assert [c["start"] for c in edl["clips"]] == sorted(c["start"] for c in edl["clips"])
    assert all(a["end"] < b["start"] for a, b in zip(edl["clips"], edl["clips"][1:]))
    assert edl["recap"]["lines"] and edl["schema"] == "touchline.reel/1"
    for c in goals:  # each goal clip contains its shot
        shot = [e for e in demo.events if e.type == "shot" and e.outcome == "goal" and c["start"] <= e.t <= c["end"]]
        assert shot


def test_camera_roundtrip():
    cam = Camera(tx=40, ty=31)
    for x, y in ((10, 5), (52.5, 34), (95, 60)):
        px, _ = cam.project(np.array([[x, y, 0.0]]))
        gx, gy = cam.to_ground(*px[0])
        assert abs(gx - x) < 1e-6 and abs(gy - y) < 1e-6


def test_broadcast_template_contract():
    html = (Path(__file__).resolve().parents[1] / "web" / "templates" / "touchline-graphics.html").read_text()
    for fn in ("window.play", "window.stop", "window.next", "window.update", "SPXGCTemplateDefinition", "templateData"):
        assert fn in html


def test_speech_ssml_is_escaped():
    x = Speech.ssml('Varga <scores> & "wins"', "es")
    assert "&lt;scores&gt;" in x and "es-ES" in x


def test_reel_multiple_favourites_and_both_clubs(demo):
    one = plan_reel(demo, club="home", player="h9", lang="en")
    many = plan_reel(demo, club="both", player="h9,a9,a7", lang="en")
    assert many["players"] == ["a7", "a9", "h9"]
    assert sum(c["focus"] in ("a9", "a7") for c in many["clips"]) >= sum(c["focus"] in ("a9", "a7") for c in one["clips"])
    goals = [c for c in many["clips"] if c["kind"] == "goal"]
    assert len(goals) == demo.state.score["home"] + demo.state.score["away"]
