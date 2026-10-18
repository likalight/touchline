import statistics

from touchline.analytics.models import get_models, shot_features
from touchline.analytics.state import MatchState, win_probability
from touchline.schema import Event
from touchline.sim.engine import simulate


def test_simulator_is_deterministic():
    _, a = simulate(11)
    _, b = simulate(11)
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]


def test_simulator_is_football_realistic():
    goals, shots, passes, completion = [], [], [], []
    for seed in range(8):
        _, evs = simulate(seed)
        goals.append(sum(e.type == "goal" for e in evs))
        shots.append(sum(e.type == "shot" for e in evs))
        ps = [e for e in evs if e.type == "pass"]
        passes.append(len(ps))
        completion.append(sum(e.outcome == "complete" for e in ps) / len(ps))
        assert evs[-1].type == "full_time"
        assert all(isinstance(e, Event) for e in evs)
    assert 1.0 <= statistics.mean(goals) <= 4.5
    assert 15 <= statistics.mean(shots) <= 32
    assert 800 <= statistics.mean(passes) <= 1400
    assert 0.74 <= statistics.mean(completion) <= 0.9


def test_xg_is_monotonic_in_distance_and_explainable():
    m = get_models()
    _, evs = simulate(3)
    shot = next(e for e in evs if e.type == "shot")
    f = shot_features(shot)
    near, far = dict(f), dict(f)
    near["distance_m"], far["distance_m"] = 8, 25
    assert m.xg.predict(near) > m.xg.predict(far)
    contrib = m.xg.explain(f, m.shot_baseline)
    assert all({"feature", "label", "logodds"} <= set(c) for c in contrib)


def test_counterfactual_improves_chance():
    m = get_models()
    f = {"bias": 1, "distance_m": 18, "angle_rad": 0.35, "header": 1, "under_pressure": 1, "assisted": 0, "blockers": 1}
    cf = m.counterfactual_shot(f)
    assert cf and cf["xg_after"] > m.xg.predict(f)


def test_win_probability_is_a_distribution():
    wp = win_probability(1, 0, 0.8, 1.1)
    assert abs(sum(wp.values()) - 1) < 1e-9
    assert win_probability(2, 0, 0, 0)["home"] == 1.0


def test_state_tracks_score_and_records():
    meta, evs = simulate(5)
    s = MatchState(meta)
    for e in evs:
        s.apply(e)
    goals = [e for e in evs if e.type == "goal"]
    assert s.score["home"] + s.score["away"] == len(goals)
    assert s.status == "full_time"
    assert sum(s.possession_pct().values()) in (99, 100, 101)
    assert {"top_speed_kmh", "fastest_shot_kmh"} <= set(s.records)
