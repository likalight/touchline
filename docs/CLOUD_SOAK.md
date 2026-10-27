# Bounded external cloud streaming experiment

Result: **PASSED**. 12 of 12
attempted clients met every gate. Elapsed: 206.68 seconds; seed 221, 30.0× playback.

Target: https://ca-touchline-3a2uvrfhbicqc.livelytree-3fdb8286.southeastasia.azurecontainerapps.io. Session: `m-f1d99cf3`. Operator deployment reference: `b13985bb2b7267a8d8b8685059b38620540e072c@sha256:bd19893ca31ef290ec8157981e3e2108fdde148bb826d37290e296bd36b563cd`.
The complete server dataset contained **1923 events**; expected final score: `{'home': 1, 'away': 1}`.
0 source events were missed by every client. Failed connections stay in the denominator.
Startup events are included via the normal recent-event replay; none are silently removed from completeness.

| Client | Connected | Source events received | Missing | Final score correct | Error |
|---|---|---|---|---|---|
| 1 | True | 1923/1923 | 0 | True | none |
| 2 | True | 1923/1923 | 0 | True | none |
| 3 | True | 1923/1923 | 0 | True | none |
| 4 | True | 1923/1923 | 0 | True | none |
| 5 | True | 1923/1923 | 0 | True | none |
| 6 | True | 1923/1923 | 0 | True | none |
| 7 | True | 1923/1923 | 0 | True | none |
| 8 | True | 1923/1923 | 0 | True | none |
| 9 | True | 1923/1923 | 0 | True | none |
| 10 | True | 1923/1923 | 0 | True | none |
| 11 | True | 1923/1923 | 0 | True | none |
| 12 | True | 1923/1923 | 0 | True | none |

For 1922 of 1922 eligible post-start source events received by
every attempted client, receipt spread was p50 **2.913 ms**, p95 **6.556 ms**, max **20.483 ms**.
This is the gap between earliest and latest client receipt on one observer machine. It is **not end-to-end latency**.
Startup replay events are excluded only from this spread statistic, never from completeness.

One bounded synthetic match; clients run on one external observer machine against one deployment. Not an SLA, maximum capacity, multi-replica, reconnect or real-match test. No server-to-client latency is claimed.
Run error: `None`. Cleanup: not_needed.
The accompanying JSON retains every client's missing IDs, unexpected IDs, order and arrival timestamps plus source hashes.
No public model calls or shared `demo`/`live` controls are used. Only the new isolated match is created and controlled.
The match uses the normal outbound pipeline: synthetic insights and its final synthetic package may be delivered to
configured downstream consumers. Downstream delivery is not verified by this streaming experiment.
