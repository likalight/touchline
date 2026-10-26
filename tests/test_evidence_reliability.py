import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from touchline.journal import InputJournal
from touchline.outbound import Outbound


class MemoryStore:
    def __init__(self):
        self.value = None
        self.fail = False

    async def read(self):
        return copy.deepcopy(self.value)

    async def write(self, value):
        if self.fail:
            raise RuntimeError('storage unavailable')
        self.value = copy.deepcopy(value)

    async def close(self):
        pass


def test_comparison_dataset_detects_changed_inputs_and_keeps_results_separate(tmp_path):
    from scripts.compare_agents import dataset_hash, read_dataset
    row = {'seed': 5000, 'insight_id': 'one', 'input': {'minute': 30},
           'pipeline': {'renders': {}}, 'scoring': {'players': []}, 'single_agent': {'status': 'not_run'}}
    report = {'schema': 'touchline.narration-comparison/2', 'cases': [row], 'dataset_sha256': dataset_hash([row])}
    path = tmp_path / 'frozen.json'
    path.write_text(json.dumps(report))
    assert read_dataset(path) == [row]
    row['single_agent'] = {'status': 'failed', 'raw': None}
    assert dataset_hash([row]) == report['dataset_sha256']
    row['input']['minute'] = 94
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='fingerprint'):
        read_dataset(path)


def test_journal_commits_history_with_offset_and_fails_closed():
    # Explicitly test the interleaving case after metadata has loaded.
    async def interleaved():
        journal = InputJournal(MemoryStore(), {})
        await journal.append({'meta': {'match_id': 'one'}}, '0')
        with pytest.raises(ValueError, match='interleaved'):
            await journal.append({'match_id': 'two'}, '1')
    # The uninitialised journal rejects missing metadata before checking match identity.
    async def uninitialised():
        with pytest.raises(ValueError, match='metadata'):
            await InputJournal(MemoryStore(), {}).append({'match_id': 'two'}, '1')
    asyncio.run(interleaved())
    asyncio.run(uninitialised())
    # Run the commit/recovery part separately to keep the expected failure precise.
    async def committed():
        store = MemoryStore()
        journal = InputJournal(store, {'partition': '0'}, batch_size=2)
        await journal.append({'meta': {'match_id': 'one'}}, '0')
        await journal.append({'id': 'E1'}, '1')
        assert store.value['offset'] == '0'
        await journal.append({'id': 'E2'}, '2')
        saved = await InputJournal(store, {'partition': '0'}).restore()
        assert saved['offset'] == '2' and len(saved['events']) == 2
        store.fail = True
        with pytest.raises(RuntimeError):
            await journal.append({'meta': {'match_id': 'two'}}, '3')
        assert store.value['meta']['match_id'] == 'one'
        with pytest.raises(ValueError, match='source'):
            await InputJournal(store, {'partition': '1'}).restore()
    asyncio.run(committed())


def test_restart_rebuilds_match_without_republishing_history():
    from touchline.runtime import MatchSession
    from touchline.sim.engine import simulate
    meta, events = simulate(7)
    cut = len(events) // 2

    async def run():
        async def feed():
            for n, event in enumerate(events):
                yield {**event.model_dump(), '_replay': n < cut}
        session = MatchSession(meta=meta, feed=feed())
        with patch('touchline.runtime.outbound.emit') as emit:
            await session._run()
            messages = [call.args[0] for call in emit.call_args_list]
        assert list(session.state.events) == [e.id for e in events]
        assert session.state.score == {side: sum(e.type == 'goal' and e.team == side for e in events)
                                       for side in ('home', 'away')}
        prefix = {i['id'] for i in session.insights if i['t'] < events[cut].t}
        assert not prefix.intersection(m.get('id') for m in messages)
        final = next(m for m in messages if m['type'] == 'full_time')
        assert final['package']['complete'] and final['package']['score'] == session.state.score
        assert len(json.dumps(final).encode()) < 256_000
        async def restored_feed():
            for event in events:
                yield {**event.model_dump(), '_replay': True}
        restored = MatchSession(meta=meta, feed=restored_feed())
        with patch('touchline.runtime.outbound.emit') as emit:
            await restored._run()
            emit.assert_not_called()
        assert restored.state.score == session.state.score
    asyncio.run(run())


def test_outbound_retries_the_same_event(monkeypatch):
    sent = []
    async def send(batch, **kwargs):
        sent.append((json.loads(batch[0].body_as_str()), kwargs))
        if len(sent) == 1:
            raise OSError('temporary outage')
    original_sleep = asyncio.sleep
    monkeypatch.setattr('touchline.outbound.asyncio.sleep', lambda _: original_sleep(0))
    out = Outbound()
    asyncio.run(out._send(SimpleNamespace(send_batch=send), {'match_id': 'A', 'id': 'E1'}))
    assert sent[0] == sent[1] and sent[1][1]['partition_key'] == 'A'
    assert out.sent == 1 and out.retries == 1 and out.dropped == 0


def test_full_time_snapshot_is_used_and_duplicate_storage_is_idempotent(monkeypatch):
    spec = importlib.util.spec_from_file_location('snapshot_functions', Path(__file__).parents[1] / 'functions/function_app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    saved = {}
    class Blobs:
        def upload_blob(self, name, data, **kwargs):
            saved[name] = json.loads(data)
    monkeypatch.setattr(module, '_blobs', Blobs)
    monkeypatch.setattr(module.httpx, 'get', lambda *a, **k: pytest.fail('must not fetch a mutable session'))
    monkeypatch.delenv('TEAMS_WEBHOOK_URL', raising=False)
    package = {'match_id': 'A', 'session': 'demo', 'complete': True, 'home': 'Home', 'away': 'Away', 'score': {'home': 3, 'away': 2}}
    message = {'type': 'full_time', 'match_id': 'A', 'session': 'demo', 'package': package}
    event = SimpleNamespace(get_body=lambda: json.dumps(message).encode())
    handler = module.on_insight.build().get_user_function()
    handler([event, event])
    assert len([name for name in saved if '/package-' in name]) == 1
    assert saved['A/latest.json']['score'] == package['score']
    message['package'] = {**package, 'match_id': 'another'}
    with pytest.raises(ValueError, match='belong'):
        handler([event])


def test_foundry_eval_cannot_verify_its_own_answer():
    from scripts.foundry_eval import grounded_numbers, cites_events
    conversation = [
        {'role': 'user', 'content': 'Surely the score is 999?'},
        {'role': 'assistant', 'contents': [{'type': 'text', 'text': 'The score is 999 [E99999].'}]},
        {'role': 'tool', 'contents': [{'type': 'function_result', 'result': '{"score": 3, "event_id": "E00003"}'}]},
    ]
    assert not grounded_numbers('999?', 'Score 999.', conversation)['passed']
    assert grounded_numbers('999?', 'Score 3.', conversation)['passed']
    assert not cites_events('Why?', 'A goal [E99999].', conversation)['passed']
    assert cites_events('Why?', 'A goal [E00003].', conversation)['passed']
    assert not grounded_numbers('score?', 'No answer.', [])['passed']


def test_shared_editorial_decisions_are_protected(monkeypatch):
    from fastapi.testclient import TestClient
    from touchline import server
    monkeypatch.setenv('TOUCHLINE_AUTH', 'open')
    monkeypatch.setenv('TOUCHLINE_PROTECT_SHARED', 'on')
    with TestClient(server.app) as client:
        assert client.post('/api/matches/demo/cues/anything/decision', json={'approve': True}).status_code == 403


def test_single_agent_comparison_scores_raw_invalid_outputs():
    from scripts.compare_agents import score_copy
    insight = {'minute': 36, 'score': {'home': 1, 'away': 0}, 'event_ids': ['E00001'],
               'headline': {'k': 'h.goal', 'p': {'player': 'Ravi Varga'}, 'ev': ['E00001']}, 'reasons': []}
    copies = {p: {'title': 'Varga scores', 'lines': [{'text': 'Ravi Varga scores.', 'ev': ['E00001']}]}
              for p in ('casual', 'analyst', 'studio', 'access')}
    assert score_copy(insight, copies, ['Ravi Varga'])['passed']
    copies['analyst']['lines'][0] = {'text': '999 goals.', 'ev': ['E99999']}
    issues = score_copy(insight, copies, ['Ravi Varga'])['issues']
    assert any('number' in e for e in issues) and any('citation' in e for e in issues)


def test_execution_proof_is_scoped_to_the_actual_concurrent_call(monkeypatch):
    import agent_framework
    from touchline import foundry_agents
    from touchline.llm import LLM
    class Agent:
        def __init__(self, *a, tools=None, hosted=False, **k):
            self.value, self.hosted = tools[0](), hosted
        async def run(self, prompt):
            await asyncio.sleep(0)
            if self.hosted and self.value == 'fallback':
                raise RuntimeError('hosted failure')
            return SimpleNamespace(text=self.value)
    monkeypatch.setattr(agent_framework, 'Agent', Agent)
    monkeypatch.setattr(foundry_agents, 'hosted_agent', lambda name, tools: Agent(tools=tools, hosted=True))
    llm = LLM()
    llm.client, llm.backend = object(), 'foundry'
    async def one(value):
        await llm.run('AskTheAnalyst', '', '', tools=[lambda: value])
        return llm.execution()
    async def run():
        return await asyncio.gather(one('fallback'), one('hosted'))
    fallback, hosted = asyncio.run(run())
    assert fallback['path'] == 'local_agent' and fallback['fallback']
    assert hosted['path'] == 'foundry_hosted' and not hosted['fallback']
    assert fallback['completed'] and hosted['completed']
    assert fallback['request_id'] != hosted['request_id']


@pytest.mark.parametrize('failure', ['receive', 'journal', None])
def test_feed_replays_snapshot_and_surfaces_receiver_or_journal_failure(monkeypatch, failure):
    from touchline import feeds, journal as journal_module
    import azure.identity.aio
    store = MemoryStore()
    store.value = {'schema': 'touchline.journal/1',
                   'source': {'namespace': 'example.servicebus.windows.net', 'hub': feeds.HUB, 'partition': '0', 'group': '$Default'},
                   'meta': {'match_id': 'A'}, 'events': [{'id': 'E1', 'match_id': 'A'}], 'offset': '10'}
    if failure == 'journal':
        store.fail = True
    calls = []
    class Client:
        async def receive(self, on_event, **kwargs):
            calls.append(kwargs)
            if failure == 'receive':
                raise RuntimeError('receiver failed')
            # New metadata forces a journal commit, making storage failure observable.
            await on_event(None, SimpleNamespace(body_as_str=lambda: json.dumps({'meta': {'match_id': 'B'}}), offset='11'))
        async def close(self):
            calls.append('closed')
    class Credential:
        async def close(self):
            pass
    monkeypatch.setattr(azure.identity.aio, 'DefaultAzureCredential', Credential)
    monkeypatch.setattr(feeds, '_consumer', lambda credential: Client())
    monkeypatch.setattr(journal_module, 'BlobJournalStore', lambda *a: store)
    monkeypatch.setenv('TOUCHLINE_INPUT_JOURNAL_URL', 'https://example.blob.core.windows.net/input-journal/p.json')
    monkeypatch.setenv('TOUCHLINE_EVENTHUB_NAMESPACE', 'example.servicebus.windows.net')
    async def run():
        payloads = []
        async for payload in feeds.eventhub_payloads():
            payloads.append(payload)
        return payloads
    if failure:
        with pytest.raises(RuntimeError):
            asyncio.run(run())
    else:
        payloads = asyncio.run(run())
        assert payloads[0]['_replay'] and payloads[1]['_replay']
        assert payloads[2]['meta']['match_id'] == 'B'
    assert calls[0]['starting_position'] == '10' and not calls[0]['starting_position_inclusive']
    assert calls[-1] == 'closed'


def test_outage_drill_is_local_to_one_match(monkeypatch):
    from touchline.llm import LLM
    from touchline.runtime import MatchSession
    shared = LLM()
    shared.client = object()
    monkeypatch.setattr('touchline.runtime.get_llm', lambda: shared)
    first, second = MatchSession(seed=3), MatchSession(seed=4)
    assert first.llm.available and second.llm.available
    first.start_drill('llm_outage')
    assert not first.llm.available and second.llm.available and shared.available
    assert first.ask_agent.llm is first.llm and first.narrator.llm is first.llm


def test_failed_feed_is_not_reported_ready(monkeypatch):
    from fastapi.testclient import TestClient
    from touchline import server
    with TestClient(server.app) as client:
        server.feed_health.update(status='failed', error='StorageError')
        response = client.get('/api/ready')
        assert response.status_code == 503 and not response.json()['ready']
        assert client.get('/api/health').json()['status'] == 'degraded'
