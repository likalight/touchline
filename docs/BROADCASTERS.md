# Touchline for broadcasters and streamers

Touchline turns a live event feed into explained, verified, personalised graphics and
stories. It is built so a studio can trust it on air, a streaming product can personalise
with it, and an engineering team can run it.

## Where it fits in a match-day workflow

| Moment | What Touchline does | Interface |
|---|---|---|
| Pre-match | Simulated or real event feed connected; producer chooses auto-air or review | Event Hubs / SSE / `POST /api/matches` |
| Live: graphics desk | Timed lower-thirds, side panels and player tags on the match clock, with priorities and pre-emption | `touchline.overlay/1` cues; CasparCG / SPX template `web/templates/touchline-graphics.html` |
| Live: producer | Approve or drop each graphic; goals and red cards always air | Producer console, `POST /cues/{id}/decision` |
| Live: commentary and studio | Storylines with callbacks ("redemption for Varga"); ask the analyst anything | Insight feed, `POST /ask`, A2A agent card |
| Live: streaming app | Every viewer picks a mode, language, club, player or single metric | Live app; `GET /insights?persona=&lang=` |
| Live: accessibility | Spoken description of where play is, two-voice commentary, neural voices via Azure AI Speech | Audio description mode, `/api/speak` |
| Half-time and full-time | Recaps that find the story (comeback, ten men, late winner) | `GET /recap?persona=&lang=` |
| Post-match | A personal highlights reel per fan, and an edit list for the studio | `GET/POST /reel` (MP4 + EDL) |

## Latency budget

Broadcast graphics play against a 20 ms frame (50 fps) and live streams typically run
several seconds behind the stadium. Touchline's deterministic path is well inside one
frame; language-model work never sits on the hot path.

| Stage | Measured (p50 / p95) |
|---|---|
| Event to updated match state | about 0.15 / under 1 ms |
| Moment to verified, rendered cue (analyst, storyline, fact-check, 4 narrators x 4 languages, editorial producer, commentary) | See the current measured p50 / p95 in EVAL.md (server pipeline only) |
| Extra language via Azure OpenAI (async; arrives as a `render` update) | model-bound, typically sub-second |
| Personal highlights reel (75 s, 1280x720, H.264) | about 45 s on 1 vCPU |

Measured by `scripts/evaluate.py` on 12 unseen matches (see `docs/EVAL.md`).

## Trust: why it is safe to put on air

- **Every number is re-derived.** The FactChecker recomputes xG, pass difficulty, speeds,
  distances, win probability and every storyline count from the raw events before a
  graphic can air. 735 of 735 insights verified in evaluation; tampered or invented
  numbers are blocked (tested, and demonstrated live by the resilience drills).
- **No future leakage.** Analysis runs in step with the feed, so an insight can only use
  what had happened when it was written. The checker rejects any citation to a later event.
- **Language models are optional and contained.** They rewrite or translate verified
  copy only; any unsupported number or player name is rejected and the deterministic copy
  airs instead. A circuit breaker drops to phrase banks if the model degrades.
- **A human can stay in control.** Review mode holds every non-critical graphic for approval.
- **Full audit trail.** Every agent hand-off is a span (`/audit`, Application Insights),
  every claim cites event IDs, and every match's data can be exported.
- **Rights-safe by construction.** Synthetic data, fictional clubs and players; no
  third-party marks.

## Resilience

The IngestGuard repaired a feed with 10% corrupt, duplicated and out-of-order events
exactly once and in order in every evaluation match. Language-model and speech failures
degrade to deterministic copy and browser voices without interrupting the show.

## Cost per match

Usage per 90-minute match (from the evaluation runs):

| Resource | Usage per match | Notes |
|---|---|---|
| Container Apps compute | about 7,200 vCPU-seconds (1 vCPU, about 2 hours with warm-up) | The monthly free grant is 180,000 vCPU-seconds and 360,000 GiB-seconds per subscription, so about 25 matches a month run inside it ([pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/)) |
| Azure OpenAI, one extra language | about 56 moments x 4 personas = 224 calls; about 80k input and 20k output tokens | At $0.40 / $1.60 per million tokens (gpt-4.1-mini standard rate listed on [cloudprice.net](https://cloudprice.net/models/gpt-4.1-mini); confirm for your region) about **$0.06 per match per extra language** |
| Azure AI Speech, audio description | about 8,000 characters per listener per match | Free tier includes 0.5 million neural characters a month ([pricing](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services)) |
| Personal reel | about 1 vCPU-minute and about 1,000 voiced characters | Rendered on demand and cached |

English, Spanish, French and Portuguese cost nothing beyond compute: they are rendered
from verified phrase banks.

## Deployment and scale

- `azd up` provisions Container Apps, Container Registry, Microsoft Foundry (project and
  model deployment), Event Hubs, Log Analytics, Application Insights and a managed
  identity with least-privilege roles. No secrets.
- One match is one session. The judged deployment pins one warm replica because state is process-local;
  shared durable state is required before scaling replicas. Judge Mode uses a separate replay per visitor.
- Event Hubs partitions by match ID, so many concurrent matches ingest independently.
- Every verified insight also streams out on a second hub; the `packages` Azure Function
  (Flex Consumption) builds social cards and the post-match package for your CMS.
- Producer tools sit behind Microsoft Entra ID sign-in with a Producer role; fan questions
  pass Azure AI Content Safety Prompt Shields. See [GOVERNANCE.md](GOVERNANCE.md).

## Rollout we would propose

1. **Studio desk pilot.** Producer console in review mode alongside an existing graphics
   operator; measure approval rate and time saved.
2. **Second-screen app.** Personal modes and languages for a subset of streaming viewers.
3. **Localised feeds and accessibility.** Audio description and extra languages per market.
4. **Post-match.** Personal reels pushed to fans of each club.
