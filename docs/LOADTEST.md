# Load test: fans per replica

`python scripts/loadtest.py --fans 100 250 500 1000 --seconds 30` runs one server process (one Python
worker, about one vCPU, like a Container Apps replica with `cpu: 1.0`), plays a match at **10x speed** (ten times a
real match's event rate, so this is conservative), and connects every fan to the live stream for 30 seconds.
Fan-out lag is the gap between the first and the last fan receiving the same match event.

This historical experiment ran clients and server on the same machine. It cannot isolate the
contributions of the load generator, server and network to delivery lag. It has not been repeated
on the deployed Azure topology for this revision.

| Fans | Connected | Received every event | Fan-out lag p50 / p95 | Server CPU | Memory |
|---|---|---|---|---|---|
| 100 | 100 | 100% | 12.2 / 20.5 ms | 5% | 133 MiB |
| 250 | 250 | 100% | 27.2 / 41.0 ms | 11% | 143 MiB |
| 500 | 500 | 100% | 59.3 / 443.2 ms | 24% | 151 MiB |
| 1,000 | 1,000 | 100% | 153.1 / 3521.1 ms | 47% | 177 MiB |

At 1,000 connections the measured p95 fan-out lag was 3.5 seconds. Events in the last two
seconds are excluded from completeness, and the denominator is the union seen by clients;
an event missed by every client is not detected. These results do not establish full-match
capacity or acceptable real-time delivery at 1,000 fans.

The current app runs on one warm replica. Scale-out requires shared session state and input
ownership. The runner now rejects an empty sample and uses a 500 ms p95 fan-out target in
addition to connections, completeness and CPU when reporting a passing short-run count.
Those stricter gates were not applied to the historical numbers above.

A historical compute-only estimate of $0.22 for a two-hour 1-vCPU/2-GiB window excluded Event
Hubs, storage, Functions, monitoring, networking, model calls and speech. It is neither a
current Azure quote nor a measured cost per 1,000 fans. Obtain deployment-specific pricing
and a sustained external load result before making cost or capacity claims.
