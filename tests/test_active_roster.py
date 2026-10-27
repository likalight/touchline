"""A red card changes football participation, not just the commentary."""
import pytest

from touchline.sim.engine import MatchSimulator, simulate


@pytest.mark.parametrize("seed", [7, 87, 150, 221, 393])
def test_dismissed_players_never_return(seed):
    meta, events = simulate(seed)
    dismissed = set()
    for event in events:
        assert event.player_id not in dismissed, (seed, event.id, event.player_id)
        assert event.target_id not in dismissed, (seed, event.id, event.target_id)
        if event.type == "card" and event.outcome in {"red", "second_yellow"}:
            dismissed.add(event.player_id)
        if event.frame is not None:
            assert not dismissed.intersection(event.frame)
            assert len(event.frame) == 22 - len(dismissed)
    if seed == 221:
        assert "h8" in dismissed  # regression: formerly 91 later actions
    assert len(meta.home.players) == len(meta.away.players) == 11


def test_dismissed_carrier_and_corner_takers_are_replaced():
    sim = MatchSimulator(221)
    sim.dismiss("h9")
    assert sim.carrier != "h9"
    for pid in ["h7", "h10", "h11"]:
        sim.dismiss(pid)
    sim.give_ball("home", 70, 20, prefer="h9")
    assert sim.carrier not in sim.dismissed
    corner = list(sim.corner("home"))[0]
    assert corner.player_id not in sim.dismissed
    for side in ["home", "away"]:
        kickoff = list(sim.kickoff(side))[0]
        assert kickoff.player_id not in sim.dismissed
        assert not sim.dismissed.intersection(kickoff.frame)


def test_remaining_players_keep_their_formation_anchors():
    before, after = MatchSimulator(7), MatchSimulator(7)
    after.dismiss("h2")
    list(before.kickoff("home")); list(after.kickoff("home"))
    for pid in after.pos:
        assert after.pos[pid] == before.pos[pid]
    before.rng.gauss = after.rng.gauss = lambda *args: 0
    before.reshape(); after.reshape()
    for pid in after.pos:
        assert after.pos[pid] == before.pos[pid]


def test_emergency_keeper_is_used_for_shots_and_restarts():
    sim = MatchSimulator(7)
    sim.dismiss("a1")
    keeper = sim.keepers["away"]
    assert keeper != "a1" and keeper not in sim.dismissed
    events = list(sim.run())
    assert all(e.player_id != "a1" and e.target_id != "a1" for e in events)
    assert any(e.type == "shot" and e.team == "home" for e in events)
    for event in events:
        if event.type == "shot" and event.team == "home":
            assert event.qualifiers["goalkeeper_id"] == keeper
        if event.type == "save" and event.team == "away":
            assert event.player_id == keeper
    list(sim.restart_out("home", (104, 34)))
    assert sim.carrier == keeper


def test_fewer_than_seven_players_abandons_before_kickoff():
    sim = MatchSimulator(7)
    for pid in ["h2", "h3", "h4", "h5", "h6"]:
        sim.dismiss(pid)
    events = list(sim.run())
    assert len(events) == 1
    assert events[0].type == "full_time"
    assert events[0].qualifiers["status"] == "abandoned"
