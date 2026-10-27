"""Record real local pipeline failure drills; no cloud/model calls or outbound publishing."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def measure(seed=87):
    os.environ['TOUCHLINE_LLM'] = 'off'
    from touchline.llm import reset_llm
    reset_llm()
    from touchline.runtime import MatchSession
    session = MatchSession(seed=seed, speed=1000)
    session.broadcast_outputs = False
    session.control('jump', 200)
    original_play = session._play
    names = ('feed_storm', 'narrator_crash', 'storyline_crash', 'hallucination')
    injected = False

    async def play(event, realtime=False):
        nonlocal injected
        if not injected and event.seq >= 200:
            injected = True
            for name in names:
                session.start_drill(name)
        await original_play(event, realtime=realtime)

    session._play = play
    await session._run()
    drills = [session._public_drill(d) for d in session.drills]
    escaped = [i['id'] for i in session.insights if any(
        '99th' in line['text'] for variants in i.get('renders', {}).values()
        for render in variants.values() for line in render['lines'])]
    checks = {
        'all_four_drills_detected_and_recovered': len(drills) == 4 and all(d['detected_by'] and d['recovered'] for d in drills),
        'no_injected_claim_in_rendered_copy': not escaped,
        'events_applied_once': session.guard.stats['accepted'] == len(session.events) == len(session.state.events),
        'analyst_stand_in_used': any(r.get('source') == 'fallback:studio' for i in session.insights
                                   for r in i.get('renders', {}).get('analyst', {}).values()),
        'match_completed': session.done and session.state.status == 'full_time',
    }
    digest = hashlib.sha256()
    for directory in ('touchline', 'scripts', 'tests', 'web', 'infra'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.suffix in {'.py', '.js', '.cjs', '.html', '.css', '.bicep'}:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
    return {'schema': 'touchline.recovery-evidence/1', 'observed_at': datetime.now(timezone.utc).isoformat(),
            'source_sha256': digest.hexdigest(), 'seed': seed, 'injected_at_sequence': 200,
            'passed': all(checks.values()), 'checks': checks, 'drills': drills,
            'final_score': session.state.score, 'insights': len(session.insights),
            'ingest': session.guard.stats, 'escaped_insight_ids': escaped,
            'scope': 'Accelerated local synthetic replay, four controlled faults injected together. '
                     'No hosted model, Azure outage, process restart, network latency or production recovery SLA is measured.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(measure())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': report['checks'], 'output': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
