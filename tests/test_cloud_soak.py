"""The external experiment must not turn common loss into apparent completeness."""
import asyncio
import json

import pytest

from scripts.cloud_soak import Observation, expected_score, messages, source_dataset, summarize


EVENTS = [
    {"id": "E1", "seq": 1, "match_id": "M1", "type": "goal", "team": "home"},
    {"id": "E2", "seq": 2, "match_id": "M1", "type": "goal", "team": "away"},
    {"id": "E3", "seq": 3, "match_id": "M1", "type": "full_time", "team": None},
]


def observed(client, ids=("E1", "E2", "E3"), offset=0):
    return Observation(client, hello=True, done=True, final_score={"home": 1, "away": 1},
                       arrivals={eid: 100 * (i + 1) + offset for i, eid in enumerate(ids)}, order=list(ids))


def dataset(events=EVENTS, seed=221):
    return "\n".join(json.dumps(row) for row in [
        {"meta": {"match_id": "M1", "seed": seed, "synthetic": True}}, *events])


def test_same_event_lost_by_every_client_remains_in_every_denominator():
    report = summarize(EVENTS, [observed(i, ("E1", "E3")) for i in range(12)], set())
    assert not report["passed"]
    assert report["source_event_count"] == 3
    assert report["all_clients_lost_ids"] == ["E2"]
    assert all(c["missing_ids"] == ["E2"] and c["expected"] == 3 for c in report["clients"])


def test_failed_client_is_not_removed_from_completeness_or_fanout_denominator():
    report = summarize(EVENTS, [observed(1), Observation(2, error="ConnectError")], set())
    assert report["clients_attempted"] == 2
    assert report["clients_connected"] == report["clients_passed"] == 1
    assert report["complete_client_share"] == .5
    assert report["clients"][1]["missing_ids"] == ["E1", "E2", "E3"]
    assert report["fanout_receipt_spread"]["events_observed_by_every_client"] == 0
    assert report["fanout_receipt_spread"]["p95_ms"] is None
    assert not report["passed"]


def test_complete_match_checks_score_and_excludes_startup_only_from_spread():
    clients = [observed(1), observed(2, offset=8)]
    clients[1].arrivals["E1"] = 4000  # replay timing must not inflate live spread
    report = summarize(EVENTS, clients, {"E1"})
    assert report["passed"]
    assert report["source_event_count"] == 3
    assert report["expected_final_score"] == {"home": 1, "away": 1}
    assert report["fanout_receipt_spread"]["eligible_source_events"] == 2
    assert report["fanout_receipt_spread"]["max_ms"] == 8
    assert "Not server latency or end-to-end latency" in report["fanout_receipt_spread"]["scope"]
    clients[1].arrivals.pop("E1")
    assert not summarize(EVENTS, clients, {"E1"})["passed"]


@pytest.mark.parametrize("defect", ["score", "duplicate", "order", "unexpected", "unfinished"])
def test_other_client_failure_gates(defect):
    client = observed(1)
    if defect == "score":
        client.final_score = {"home": 2, "away": 0}
    elif defect == "duplicate":
        client.duplicates = 1
    elif defect == "order":
        client.order = ["E2", "E1", "E3"]
    elif defect == "unexpected":
        client.arrivals["EXTRA"] = 500
    else:
        client.done = False
    assert not summarize(EVENTS, [client], set())["passed"]


def test_empty_source_or_empty_clients_cannot_pass():
    assert not summarize([], [Observation(1, hello=True, done=True, final_score={"home": 0, "away": 0})], set())["passed"]
    assert not summarize(EVENTS, [], set())["passed"]


def test_source_validation_requires_full_requested_match_and_unique_ordered_identities():
    meta, events = source_dataset(dataset(), 221)
    assert meta["seed"] == 221 and expected_score(events) == {"home": 1, "away": 1}
    for invalid in [dataset(seed=222), dataset(EVENTS[:-1]),
                    dataset([EVENTS[0], dict(EVENTS[1], id="E1"), EVENTS[2]]),
                    dataset([EVENTS[0], dict(EVENTS[1], seq=4), EVENTS[2]]),
                    dataset([EVENTS[0], dict(EVENTS[1], match_id="other"), EVENTS[2]])]:
        with pytest.raises(ValueError):
            source_dataset(invalid, 221)


def test_sse_parser_ignores_comments_and_reads_multiline_frames():
    class Response:
        async def aiter_lines(self):
            for line in [": keep-alive", "", "event: state", 'data: {"score":',
                         'data: {"home": 1, "away": 1}}', "", "event: done", 'data: {}', ""]:
                yield line
    async def run():
        return [item async for item in messages(Response())]
    assert asyncio.run(run()) == [("state", {"score": {"home": 1, "away": 1}}), ("done", {})]
