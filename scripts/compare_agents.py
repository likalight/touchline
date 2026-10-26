"""Bounded single-agent narration comparison on frozen, held-out synthetic moments.

--prepare exports inputs and pipeline references without a model call.
--run uses the configured Foundry model and records raw baseline outputs and failures.
This compares narration strategies; it does NOT prove whole-system superiority of
multi-agent orchestration. Both sides receive the same interpreted claim frames.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PERSONAS = ('casual', 'analyst', 'studio', 'access')


def dataset_hash(rows):
    """Bind both alternatives to the same frozen inputs and reference outputs."""
    frozen = [{k: row[k] for k in ('seed', 'insight_id', 'input', 'pipeline', 'scoring')} for row in rows]
    return hashlib.sha256(json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_dataset(path):
    report = json.loads(path.read_text(encoding='utf-8'))
    rows = report.get('cases', [])
    if report.get('schema') != 'touchline.narration-comparison/2' or not 1 <= len(rows) <= 24:
        raise ValueError('Expected a prepared v2 dataset with 1..24 cases.')
    if report.get('dataset_sha256') != dataset_hash(rows):
        raise ValueError('Frozen dataset fingerprint does not match.')
    return rows
INSTRUCTIONS = '''You are a single football graphics agent. Call get_context once and write
all four English audience versions of this synthetic moment. Use only its claim frames
and source facts; do not invent statistics, players, records or event IDs. Casual: plain
language, max 2 lines. Analyst: explain the evidence, max 6 lines. Studio: max 1 line.
Access: spoken description, max 3 lines. Title under 60 characters; lines under 110.
Every line must cite supporting event IDs in its ev array. Return only a JSON object:
{"casual":{"title":"...","lines":[{"text":"...","ev":["E00001"]}]},
 "analyst":{...}, "studio":{...}, "access":{...}}.'''


def score_copy(insight, renders, players):
    from touchline.agents.verifier import FactChecker
    checker = FactChecker(SimpleNamespace(players={p: SimpleNamespace(name=p) for p in players}))
    errors = []
    for persona, limit in zip(PERSONAS, (2, 6, 1, 3)):
        render = renders.get(persona) if isinstance(renders, dict) else None
        if not isinstance(render, dict) or not isinstance(render.get('title'), str) or not isinstance(render.get('lines'), list):
            errors.append(f'{persona}: missing or malformed render')
            continue
        lines = render['lines']
        if not lines or len(lines) > limit:
            errors.append(f'{persona}: invalid line count')
        texts = [render['title']]
        if len(render['title']) > 60:
            errors.append(f'{persona}: title too long')
        for line in lines:
            if not isinstance(line, dict) or not isinstance(line.get('text'), str):
                errors.append(f'{persona}: malformed line')
                continue
            texts.append(line['text'])
            if len(line['text']) > 110:
                errors.append(f'{persona}: line too long')
            ids = line.get('ev')
            if not isinstance(ids, list) or not ids or any(not isinstance(e, str) or e not in insight['event_ids'] for e in ids):
                errors.append(f'{persona}: unsupported or missing citation')
        errors.extend(f'{persona}: {e}' for e in checker.check_text(insight, texts))
    return {'passed': not errors, 'issues': errors,
            'scope': 'Format, allowed numbers/names/superlatives and event IDs; not semantic or preference scoring.'}


async def prepare(limit):
    from touchline.llm import reset_llm
    previous = os.environ.get('TOUCHLINE_LLM')
    os.environ['TOUCHLINE_LLM'] = 'off'
    reset_llm()
    items = []
    try:
        from touchline.runtime import MatchSession
        for seed in (5000, 5001, 5002, 5003, 5004, 5005):
            session = MatchSession(seed=seed, speed=1000)
            session.broadcast_outputs = False
            session.control('jump', 200)
            await session._run()
            chosen = [i for i in session.insights if i['kind'] in ('goal', 'card_red', 'hat_trick')]
            for insight in chosen:
                items.append({'seed': seed, 'insight': copy.deepcopy(insight),
                              'players': [p.name for p in session.state.players.values()],
                              'context': {'minute': insight['minute'], 'kind': insight['kind'],
                                          'frames': [insight['headline'], *insight['reasons']],
                                          'facts': [session.state.enriched[e].facts() for e in insight['event_ids']]}})
                if len(items) >= limit:
                    return items
        return items
    finally:
        if previous is None:
            os.environ.pop('TOUCHLINE_LLM', None)
        else:
            os.environ['TOUCHLINE_LLM'] = previous
        reset_llm()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path, help='Frozen --prepare dataset; required with --run')
    args = parser.parse_args()
    if not 1 <= args.limit <= 24:
        parser.error('--limit must be 1..24; model runs are deliberately bounded')
    if args.run and not args.input:
        parser.error('--run requires --input from --prepare so the cases cannot silently change')
    if args.prepare and args.input:
        parser.error('--input is only used with --run')
    if args.input and args.input.resolve() == args.output.resolve():
        parser.error('Keep the frozen input separate from the observed output')
    from touchline.llm import get_llm, _json_from
    if args.run and (not get_llm().available or get_llm().backend != 'foundry'):
        print('A configured Foundry model is required. Use --prepare for an offline dataset.', file=sys.stderr)
        return 1
    items = [] if args.run else await prepare(args.limit)
    llm = get_llm() if args.run else None
    rows = []
    for item in items:
        insight = item['insight']
        reference = {p: insight['renders'][p]['en'] for p in PERSONAS}
        row = {'seed': item['seed'], 'insight_id': insight['id'], 'input': item['context'],
               'pipeline': {'renders': reference, 'checks': score_copy(insight, reference, item['players'])},
               'scoring': {'insight': {**{k: insight[k] for k in ('headline', 'reasons', 'minute', 'event_ids')},
                                       'score': insight.get('score', {})},
                           'players': item['players']},
               'single_agent': {'status': 'not_run'}}
        rows.append(row)
    if args.run:
        rows = read_dataset(args.input)
    for row in rows:
        if llm:
            frozen = json.dumps(row['input'], ensure_ascii=False)
            calls = []
            def get_context() -> str:
                """The same interpreted frames and time-bounded source facts given to the pipeline narrators."""
                calls.append('get_context')
                return frozen
            raw = await llm.run('SingleWriterBaseline', INSTRUCTIONS, 'Write all four audience versions.',
                                timeout=20, tools=[get_context])
            try:
                rendered = _json_from(raw or '')
            except (ValueError, TypeError):
                rendered = {}
            checks = score_copy(row['scoring']['insight'], rendered, row['scoring']['players'])
            if not calls:
                checks['passed'] = False
                checks['issues'].append('The agent did not retrieve the supplied context.')
            row['single_agent'] = {'status': 'completed' if raw else 'failed', 'raw': raw,
                                   'checks': checks, 'context_tool_calls': len(calls),
                                   'execution': llm.execution()}
    report = {'schema': 'touchline.narration-comparison/2', 'observed_at': datetime.now(timezone.utc).isoformat(),
              'status': 'measured' if llm else 'prepared_not_run', 'cases': rows,
              'dataset_sha256': dataset_hash(rows),
              'summary': {'cases': len(rows), 'attempted': len(rows) if llm else 0,
                          'pipeline_format_numeric_citation_passes': sum(r['pipeline']['checks']['passed'] for r in rows),
                          'single_agent_completed': sum(r['single_agent']['status'] == 'completed' for r in rows),
                          'single_agent_format_numeric_citation_passes': sum(r['single_agent'].get('checks', {}).get('passed', False) for r in rows)},
              'scope': 'Single-agent narration versus specialist phrase-bank narration on identical interpreted inputs. '
                       'Not an end-to-end single-agent baseline, a semantic accuracy score, or evidence that more agents always win.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{report["status"]}: {len(rows)} cases written to {args.output}')
    return 1 if llm and any(r['single_agent']['status'] == 'failed' for r in rows) else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
