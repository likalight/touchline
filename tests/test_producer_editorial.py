"""The Producer is an editor: it airs, bumps, queues or drops, and says why."""
from touchline.agents.producer import Producer


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def ins(i, kind="line_break", sal=0.6, team="home", player="h8", story=None, t=600.0):
    return {"id": f"I{i}", "kind": kind, "salience": sal, "team": team, "player_id": player, "t": t, "minute": int(t // 60) + 1,
            "event_ids": [f"E{i}"], "viz": {}, "renders": {}, "verification": {"status": "verified"}, **({"storyline": story} if story else {})}


def test_air_then_drop_weaker_while_busy():
    c = Clock(); p = Producer("M", clock=c)
    a = p.schedule(ins(1, sal=0.8), 600)
    assert a["decision"]["action"] == "air" and "high news value" in a["decision"]["reason"]
    b = p.schedule(ins(2, sal=0.3, player="h4"), 601)
    assert b["decision"]["action"] == "drop" and b["approval"] == "skipped"


def test_bump_when_clearly_better():
    c = Clock(); p = Producer("M", clock=c)
    p.schedule(ins(1, kind="hard_pass", sal=0.4), 600)
    b = p.schedule(ins(2, kind="chance_saved", sal=0.9, player="h9"), 602)
    assert b["decision"]["action"] == "bump"
    bumped = p.tick()
    assert bumped and bumped[0]["approval"] == "bumped" and bumped[0]["insight_id"] == "I1"


def test_queue_then_air_when_slot_frees():
    c = Clock(); p = Producer("M", clock=c)
    p.schedule(ins(1, kind="chance_saved", sal=0.8, player="h9"), 600)
    c.t += 6.0                      # the first graphic is close to finishing
    b = p.schedule(ins(2, kind="line_break", sal=0.7, player="a8", team="away"), 606)
    assert b["decision"]["action"] == "queue" and b["approval"] == "queued"
    c.t += 3.5
    out = p.tick()
    assert out and out[0]["insight_id"] == "I2" and out[0]["approval"] == "auto" and out[0]["decision"]["action"] == "air"


def test_freshness_and_story_change_the_score():
    c = Clock(); p = Producer("M", clock=c)
    first, f1 = p.score(ins(1, kind="line_break", sal=0.6), 600)
    p.schedule(ins(1, kind="line_break", sal=0.6), 600)
    again, f2 = p.score(ins(2, kind="hard_pass", sal=0.6, player="h4"), 650)   # same family, soon after
    assert again < first and f2["fresh"] < 0
    told, f3 = p.score(ins(3, kind="story_duel", sal=0.6, story=["s.duel"]), 700)
    assert f3["story"] > 0


def test_goals_always_air_and_rundown_records_everything():
    c = Clock(); p = Producer("M", clock=c)
    p.schedule(ins(1, kind="chance_saved", sal=0.95), 600)
    g = p.schedule(ins(2, kind="goal", sal=1.0, player="h9"), 601)
    assert g["decision"]["action"] == "bump" and "must-air" in g["decision"]["reason"]
    assert [r["action"] for r in p.rundown] == ["air", "bump"]
    assert p.stats()["decisions"]["bump"] == 1


def test_card_outranks_waits_for_its_turn_instead_of_dropping():
    c = Clock(); p = Producer("M", clock=c)
    p.schedule(ins(1, kind="line_break", sal=0.5, player="h4"), 600)
    card = p.schedule(ins(2, kind="card_yellow", sal=0.3, player="a5", team="away"), 601)
    assert card["decision"]["action"] in ("queue", "bump")
    c.t += 10
    aired = [u for u in p.tick() if u["insight_id"] == "I2"]
    assert card["decision"]["action"] == "bump" or (aired and aired[0]["approval"] == "auto")


def test_variety_rule_drops_routine_repeat_but_never_news():
    c = Clock(); p = Producer("M", clock=c)
    p.schedule(ins(1, kind="line_break", sal=0.5, player="h4"), 600)
    c.t += 20
    rep = p.schedule(ins(2, kind="hard_pass", sal=0.5, player="h8"), 640)       # same family, same team, 40 s later
    assert rep["decision"]["action"] == "drop" and "same kind" in rep["decision"]["reason"]
    c.t += 20
    goal = p.schedule(ins(3, kind="goal", sal=1.0, player="h9"), 660)
    assert goal["decision"]["action"] in ("air", "bump")
