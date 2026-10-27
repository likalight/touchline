"""Exercise the deployed MCP endpoint from an external HTTP client (no model call).

This proves protocol/tool interoperability; it is not evidence of a Copilot UI run.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    exchanges = []
    with httpx.Client(base_url=args.url.rstrip('/'), timeout=30,
                      headers={'Accept': 'application/json, text/event-stream'}) as client:
        def rpc(method, params):
            response = client.post('/mcp', json={'jsonrpc': '2.0', 'id': len(exchanges)+1,
                                                'method': method, 'params': params})
            response.raise_for_status()
            payload = response.json()
            if 'error' in payload:
                raise RuntimeError(payload['error'])
            exchanges.append({'method': method, 'params': params, 'result': payload['result']})
            return payload['result']

        def call(name, arguments):
            result = rpc('tools/call', {'name': name, 'arguments': arguments})
            if result.get('isError'):
                raise RuntimeError('MCP tool returned an error')
            return json.loads(result['content'][0]['text'])

        protocol = rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                     'clientInfo': {'name': 'touchline-external-audit', 'version': '1'}})
        names = {t['name'] for t in rpc('tools/list', {})['tools']}
        matches = call('list_matches', {})
        match = next((m for m in matches if m['session'] == 'live'), matches[0])
        sid = match['session']
        scoreboard = call('get_scoreboard', {'session': sid})
        moments = call('get_key_moments', {'session': sid, 'kind': 'goal', 'limit': 1})
        if not moments:
            raise RuntimeError('Wait for a delivered goal before recording interoperability evidence')
        event_id = moments[-1]['evidence'][0]
        event = call('explain_event', {'session': sid, 'event_id': event_id})
        recap = call('get_recap', {'session': sid, 'persona': 'casual', 'lang': 'en'})
        ready = client.get('/api/ready').json()
        checks = {'protocol_negotiated': bool(protocol.get('protocolVersion')),
                  'tools_discovered': {'list_matches', 'get_scoreboard', 'explain_event', 'get_recap'} <= names,
                  'score_shape': set(scoreboard['score']) == {'home', 'away'},
                  'source_event_resolved': bool(event.get('verified_answers')),
                  'recap_source_checks': recap.get('verification', {}).get('status') == 'verified',
                  'application_ready': ready.get('ready') is True}
        report = {'schema': 'touchline.external-mcp/1', 'observed_at': datetime.now(timezone.utc).isoformat(),
                  'url': args.url, 'session': sid, 'checks': checks, 'passed': all(checks.values()),
                  'exchanges': exchanges,
                  'scope': 'Actual public Streamable HTTP MCP calls from a separate client process. No Copilot UI, model orchestration, permissions or production-SLA claim.'}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'checks': checks}))
        return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
