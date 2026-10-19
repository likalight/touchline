# Load test: fans per replica

`python scripts/loadtest.py --fans 100 250 500 1000 --seconds 30` runs one server process (one Python
worker, about one vCPU, like a Container Apps replica with `cpu: 1.0`), plays a match at **10x speed** (ten times a
real match's event rate, so this is conservative), and connects every fan to the live stream for 30 seconds.
Fan-out lag is the gap between the first and the last fan receiving the same match event.

The fans ran on the same two-vCPU machine as the server, so at high counts the lag is mostly the load generator
itself queueing; **server CPU is the capacity signal**, and it stays well below one core.

| Fans | Connected | Received every event | Fan-out lag p50 / p95 | Server CPU | Memory |
|---|---|---|---|---|---|
| 100 | 100 | 100% | 12.2 / 20.5 ms | 5% | 133 MiB |
| 250 | 250 | 100% | 27.2 / 41.0 ms | 11% | 143 MiB |
| 500 | 500 | 100% | 59.3 / 443.2 ms | 24% | 151 MiB |
| 1,000 | 1,000 | 100% | 153.1 / 3521.1 ms | 47% | 177 MiB |

p95 fan-out lag reaches 3.5 s at 1,000 fans, largely the co-located load generator. Events in
the last two seconds of each run are left out of "received every event", and each run lasts 30 seconds, not a whole match.

**One replica serves at least 1,000 live fans** with every fan receiving every event and the server under 70% of one
vCPU, at ten times the real event rate. Container Apps adds replicas on HTTP load (`maxReplicas` in
`infra/resources.bicep`).

## Cost per 1,000 fans

A 1 vCPU, 2 GiB replica for a two-hour match window costs about **$0.22** at Azure Container Apps consumption
prices (East US: $0.000024 per vCPU-second, $0.000003 per GiB-second, from the Azure Retail Prices API; the monthly free
grant is ignored here). At 1,000 fans per replica that is **about $0.22 per 1,000 fans per match** for the
live experience, before any language-model or speech usage (see [BROADCASTERS.md](BROADCASTERS.md#cost-per-match)).
