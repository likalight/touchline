# Governance, security and controls

What a broadcaster's security, legal and operations teams need to sign off Touchline for production.
Costs and the workflow fit are in [BROADCASTERS.md](BROADCASTERS.md); the models in [MODEL_CARD.md](MODEL_CARD.md).

## Data

| Question | Answer |
|---|---|
| What data does it process? | Match events (passes, shots, tackles, positions) and fan questions. In this entry every match is synthetic and every club and player is fictional. |
| Personal data? | None stored. Fans are anonymous; producers are identified only by their Microsoft Entra ID name in the audit trail. |
| Where does data live? | In the Azure region you deploy to (one `azd` parameter). Match state is in memory for the life of a session; nothing is written to disk except optional reel videos, deleted on restart. |
| Training on customer data? | No. The glass-box models (xG, pass completion, threat, win probability) are fitted on Touchline's own synthetic league and frozen ([params.json](../touchline/analytics/params.json)). Azure OpenAI does not train on prompts. |

## Layers of AI control

Every graphic, line of commentary and answer passes through these, in order. A failure at any layer means the verified fallback airs, never the unchecked text.

| Layer | What it stops | Where |
|---|---|---|
| Deterministic analytics | Made-up statistics: every number starts as a computed fact with an event ID | `touchline/analytics` |
| FactChecker agent | Any number, player or future event the match data does not support, including in model-written copy | `touchline/agents/verifier.py` |
| Azure AI Content Safety | Harmful language in model output; **Prompt Shields** on fan questions (refused before any agent sees them) | `touchline/safety.py` |
| Foundry Responsible-AI policy | Attached to every published agent version in Foundry Agent Service | `touchline/foundry_agents.py` |
| Microsoft Purview (optional) | Data-security and compliance policies on agent prompts and responses (`TOUCHLINE_PURVIEW=on`) | `touchline/llm.py` |
| Human in the loop | Review mode: graphics wait for a producer; goals, red cards and full time always air | Producer console |

## Identity and access

* **Fans:** anonymous.
* **Producers:** Microsoft Entra ID sign-in through Azure Container Apps built-in authentication. App roles `Touchline.Producer` and `Touchline.Admin` gate approving graphics, review mode, controlling the shared broadcast and running drills. Set up with `scripts/setup_entra.sh`; `TOUCHLINE_AUTH=entra` enforces it.
* **Services:** one user-assigned managed identity with least-privilege roles (AcrPull, Azure AI User, Cognitive Services OpenAI User, Cognitive Services Speech User, Cognitive Services User, Event Hubs sender and receiver). `disableLocalAuth` is on for the Foundry account, so there are **no API keys** anywhere.

## Audit

`GET /api/matches/{id}/audit` (and the download link in Agents at work) returns, per match:

* every agent hand-off as a trace span (also in Application Insights and the Foundry tracing view)
* every insight with its verification result, evidence event IDs and latency
* every editorial decision by the Producer agent (air, cut in, queue, drop) with its score and reason
* every producer action with **who did it** (Entra ID name) and when
* every resilience drill, what caught it and how long recovery took
* quarantined feed events

## Reliability

| Target | How it is met | Evidence |
|---|---|---|
| Graphics ready inside one broadcast frame | Agent pipeline p95 under 5 ms; CI fails above 250 ms | [EVAL.md](EVAL.md), run on every push |
| No wrong number on air | 100% FactChecker verification is a CI gate | [EVAL.md](EVAL.md) |
| Survives a bad feed | IngestGuard: validation, de-duplication, re-ordering; exactly-once in 100% of faulty-feed matches | [EVAL.md](EVAL.md), drills |
| Survives a model outage | Circuit breaker; hosted Foundry agent falls back to the same agent run locally, then to phrase banks | Resilience drills |
| Survives an agent crash | Agents catch and degrade; the workflow supervisor rebuilds and retries a failed run | Resilience drills, `tests/test_drills.py` |
| Stays up | Container Apps, minimum one replica, health probes, autoscale on HTTP load and Event Hubs backlog | `infra/resources.bicep` |

Resilience drills (Agents at work tab) inject each failure on demand in the live system. Building them found and fixed a real gap: the FactChecker did not treat ordinals ("99th") as numbers.

## Change management

* Agents are **versioned in Foundry Agent Service**, each version tagged with the git commit, published by `azd up`.
* CI runs the tests and the evaluation gate on every push; a regression in verification, coverage or latency fails the build.
* Foundry evaluations (quality, tool use, safety) plus Touchline's own grounding checks run with `scripts/foundry_eval.py`.

## Rolling out across a global organisation

* One deployment per broadcaster or region (`azd env new`), each with its own Foundry project, so data, agents, policies and costs stay separate.
* The overlay cue contract (`touchline.overlay/1`) and the CasparCG/SPX template keep it vendor-neutral for graphics.
* Feeds arrive through Event Hubs, so an existing data provider plugs in without code changes (`scripts/publish_feed.py` shows the format).
