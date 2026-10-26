"""A bounded, read-only demonstration of the production numeric frame checker."""
from copy import deepcopy
from datetime import datetime, timezone

from touchline.agents.verifier import FactChecker


def challenge(session, insight):
    frame = next((f for f in insight['reasons'] if f['k'] == 'r.chance_quality' and f['ev']), None)
    if frame is None:
        raise ValueError('This moment has no chance-quality claim to test.')
    event_id = frame['ev'][0]
    source = session.state.enriched.get(event_id)
    if source is None or source.xg is None:
        raise ValueError('The original shot estimate is unavailable.')
    # Do not re-evaluate historical story claims against later match state or
    # change live checker counters. This test only covers the numeric claim.
    probe = {'headline': deepcopy(frame), 'reasons': [], 't': insight['t']}
    checker = FactChecker(session.state)
    original = checker.check_insight(probe)
    expected = round(source.xg, 2)
    injected = 0.99 if expected < 0.90 else 0.01
    probe['headline']['p'].update(xg=injected, xg_pct=round(injected * 100))
    altered = checker.check_insight(probe)
    return {
        'schema': 'touchline.checker-challenge/1',
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'synthetic': True, 'insight_id': insight['id'], 'event_id': event_id,
        'metric': 'xG', 'source_value': expected,
        'original': {'value': frame['p']['xg'], **original},
        'altered': {'value': injected, **altered},
        'passed': original['status'] == 'verified' and altered['status'] == 'blocked',
        'scope': 'Runs the production numeric frame checker on isolated copies. '
                 'The source is a synthetic model estimate, not a real-world probability. '
                 'This tests one numeric mismatch, not semantic accuracy or live failure recovery.',
    }
