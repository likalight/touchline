# Touchline for a broadcaster: prototype and pilot

Touchline turns synthetic events into explained moments, player stories, timed cue contracts
and post-match packages. It is ready to demonstrate and inspect; production broadcast use
requires further validation and operational controls.

## Demonstrable workflow

| Task | Interface | Boundary |
|---|---|---|
| Inspect a moment | Match centre / Judge Mode / receipt JSON | Fictional data and model estimates |
| Preview a graphic | `touchline.overlay/1`, CasparCG/SPX HTML template | End-to-end playout not measured |
| Review queued cues | Producer console and decision API | Critical moments may auto-air; deployed human identity not yet demonstrated |
| Ask about the match | Analyst Q&A and A2A | Tool-grounded path with explicit fallback; quality evaluation required |
| Personalise | Audience, club, player and language preferences | Four phrase banks; additional generated languages need review |
| Package full time | Event Hubs → Functions → Blob | Observed synthetic packages; no transactional output-delivery guarantee |

## Timing and quality

Use the current [EVAL.md](EVAL.md) for measured server timing. The deterministic pipeline
excludes network, model, speech, rendering and playout latency. A hosted analyst smoke call
took about 5.8 seconds in one recorded observation; it is not a latency distribution.
Supported source checks reduce specific errors, but do not certify all output for broadcast.

## Cost ledger required

No current total Azure bill or per-viewer cost is published. Earlier per-language and free-grant
estimates were incomplete and should not be used as deployment costs. Account for:

- Container Apps active and idle compute, registry and storage;
- Event Hubs provisioned capacity and Functions usage;
- Foundry model input/output tokens, speech characters and safety calls;
- logs, monitoring, egress, retention and optional reel rendering.

Record region, SKU, observation window, actual usage and billed currency. Four phrase banks
avoid model calls but not infrastructure costs. Credits are a payment source, not proof of free
operation. Keep enough budget for the entire judging availability period.

## Production gates

Supported producer authentication; durable editorial history; live validation of durable outbound retry and
idempotent consumers; per-client/concurrency budgets; partition ownership for multiple matches;
external match-length soak; licensed provider integration; accessibility and operator tests.

The current input journal is designed for one writer and one active external match. Adding
replicas or partitions without ownership/state changes is not a supported scaling strategy.
See [governance](GOVERNANCE.md) and [recovery evidence](DEPLOYMENT_PROOF.md).
