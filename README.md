<div align="center">

<img src="docs/judge-editorial.png" width="100%" alt="Touchline: One player. Every turning point. The functioning judge entrance with an original AI illustration of fictional striker Ravi Varga.">

# Touchline

**Football, with memory. Watch the story. Follow the evidence.**

A Microsoft Agent Framework system that turns synthetic football events into match-long stories,
personalized graphics and broadcaster-ready outputs. Built for the Microsoft × Premier League
*Inside the Game* hackathon.

[![CI](https://github.com/likalight/touchline/actions/workflows/ci.yml/badge.svg)](https://github.com/likalight/touchline/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-f2c14e.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-0f2b20.svg)
![Microsoft Agent Framework](https://img.shields.io/badge/Agent%20Framework-1.22-0f6cbd.svg)

[Try it locally](#try-the-90-second-demo) · [Evidence](#what-we-have-measured) · [Architecture](#how-it-works) · [Deploy](#deploy-to-azure) · [Category case](docs/WINNING_CASE.md)

</div>

## Start with one story

The default app at **`/`** is the match centre: a live tactical pitch, a prominent goal story,
and a timeline that lets you revisit goals while the broadcast continues. Personalise the
view, inspect the evidence, or explore Q&A, players, alternate endings and production tools.
The same light/dark appearance follows you into Judge Mode, the phone companion and the reel.
Read the [main-app redesign and validation report](docs/MATCH_CENTRE.md).

**Player Spotlight** gives all 22 fictional players an identity, squad number,
timestamped match totals and inspectable moments. Select a player to explore their story,
then follow them on the pitch with a persistent name and shirt-number label. The camera
keeps the action ahead of a quieter stadium, and the compact opening brings the pitch
into view sooner. Statistics use only snapshots delivered to the browser; inspecting an
earlier moment does not rewind the pitch or turn current totals into historical facts.

The judge entrance now leads with an original AI illustration of Ravi Varga. That illustration
is shown only for this fictional player; other roster members have their own number treatment.
The replay brings match memory before supporting statistics, and the receipt labels its
verification result as **source checks passed**. See the [27 October visual and readiness audit](docs/VISUAL_DIAGNOSIS.md).

**Known data-validity blocker:** the seed-221 simulator can emit events involving a dismissed
player. The visual audit reproduced 91 subsequent player actions after a second yellow in
minute 29. Source agreement does not establish football consistency. Correct active-roster
handling and regenerate the demo/evaluation evidence before treating the current story as
submission-ready. This redesign does not resolve that simulator defect.

A mistake leads to a goal. The same player returns to equalize. Then comes the winner.
Touchline remembers the earlier moment and explains the connection. A fan gets the story;
an analyst gets the tactical evidence; a producer gets a timed graphics cue.

**Judge Mode** (`/judge`) takes you through three excerpts in 90 seconds. Each visitor owns
an isolated replay with pause, refresh and restart. **Match memory** puts the explanation
beside the pitch, with three chapters that unlock as their goals arrive:

- revisit a goal without interrupting the live replay, or follow the latest chapter;
- switch between Fan and Analyst explanations in place;
- follow the redemption back to the earlier loss of possession on an evidence map;
- ask what changes without the selected goal, using 1,000 model simulations per branch.

The matchday presentation supports light, dark and system themes, keyboard navigation,
reduced motion and mobile layouts. Its original generated hero is clearly labeled;
the interactive pitch and evidence map use the synthetic match data. See the
[design audit and local performance results](docs/MATCH_CENTRE.md).

Open **Evidence receipt** to:

- compare Fan and Analyst versions of the same moment;
- inspect cited events, model factors and original verification results;
- follow the recorded agent handoffs and editorial decision;
- download the complete receipt as JSON.

In Judge Mode, **Try an incorrect stat** changes one chance estimate in an isolated copy.
The real numeric checker compares the original and altered claims with the source; download
its observed verdict. This is a bounded numeric test, with the match and receipt unchanged.
The separate [recorded recovery evidence](docs/evidence/recovery.json) exercises four actual
local pipeline faults. Neither demonstration substitutes for hosted Azure recovery testing.

![An observed checker test: the original 0.07 xG claim passes, while an altered 0.99 xG copy is blocked.](docs/checker-proof.png)

All clubs, players, events and venues are fictional. Verification is against synthetic
facts and model estimates; it is not a guarantee of semantic accuracy, translation quality,
or correctness on a real football feed.

The map uses recorded event coordinates. Lines join recorded endpoints, not tracked ball
trajectories. Alternate endings are model estimates, not predictions of what really would happen.

<img src="docs/match-memory.png" width="1000" alt="Touchline Match memory: three chapter markers, a live pitch, the redemption explanation and its cited source events">

## Try the 90-second demo

Requires Python 3.12+. No Azure subscription or model key is needed for the built-in demo.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn touchline.server:app --reload
```

Open the [match centre](http://localhost:8000/) for the full experience, or
[Judge Mode](http://localhost:8000/judge) for the guided story. Select **Start demonstration**, then open a
chapter after a goal. Compare perspectives, select a memory link, and try the alternate ending.
Open its receipt to inspect the checks and download the proof. The full app at
[localhost:8000](http://localhost:8000) adds player focus, four built-in languages, commentary,
recaps, counterfactuals, a phone view and personalized highlights.

**Deployment status:** this repository contains tested deployment code. A public demo URL,
live Foundry evaluation and Azure delivery results are not yet recorded. Follow the
[deployment evidence runbook](docs/DEPLOYMENT_PROOF.md); do not treat local tests as cloud proof.

## What we have measured

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| [12-match evaluation](docs/EVAL.md) and [machine-readable results](docs/evidence.json) | Verification, goal coverage, citations, rendering and server pipeline timing on held-out synthetic matches | Real-match accuracy, browser latency, model quality or human usefulness |
| [Specialist ablation](docs/ABLATION.md) | Effects of removing the ingest guard, scout, storyline, checker and editorial scheduler | A head-to-head comparison against a capable single-agent system |
| [Single-agent comparison protocol](docs/AGENT_COMPARISON.md) | Reproducible, bounded comparison of narration strategies on identical inputs | Live-model results until the run is actually performed |
| [Load experiment](docs/LOADTEST.md) | A historical 30-second, co-located streaming experiment | Full-match capacity, multi-replica operation or an Azure SLA |
| [CI](https://github.com/likalight/touchline/actions/workflows/ci.yml) | Automated tests, evaluation gate, Bicep build and container smoke checks | Successful provisioning in a particular Azure subscription |
| [Match memory browser journey](tests/story-browser.cjs) | Full replay, navigation, original-event map, audience switching, stale-request isolation, downloads and responsive layouts | A human usability study or cross-browser accessibility certification |

CI uploads the measured evaluation JSON and report as an artifact tied to its commit.
Receipts preserve the checks performed at the original moment; opening one does not rerun
verification against the later match state. Server pipeline timing excludes model rewrites,
speech and browser delivery.

## How it works

```mermaid
flowchart LR
  A[Synthetic events] --> B[IngestGuard]
  B --> C[MomentScout]
  C --> D[TacticalAnalyst]
  D --> E[StorylineKeeper]
  E --> F[FactChecker]
  F --> G[Four audience narrators]
  G --> H[Producer]
  H --> I[Timed graphics + evidence receipts]
  I --> J[Event Hubs]
  J --> K[Azure Functions]
  K --> L[Blob packages + social cards]
```

The graph uses Microsoft Agent Framework executors, shared match state and fan-out/fan-in.
The analyst calculates interpretable xG, pass difficulty, threat and win-probability changes.
The storyline specialist tracks callbacks across the match. The checker independently
re-derives supported claims. The producer scores competing moments and explains what airs.
A supervisor and resilience drills exercise recovery when a specialist fails.

The core analytical specialists are deterministic executors, not separate language models.
Foundry provides the hosted, tool-using **Ask the analyst** agent and model-backed narration.
The four built-in languages (EN/ES/FR/PT) use phrase banks. Other languages require the model
and should be checked by fluent speakers. The answer panel distinguishes hosted execution
from local fallback using evidence from that particular request.

<details>
<summary><strong>Explore the full experience</strong></summary>

- **Football intelligence:** xG, xT, PPDA, pass difficulty, momentum, control/chaos, speed and distance.
- **Storytelling:** goal explanations, mistakes and redemption, milestones, recaps and two-voice commentary.
- **Personalization:** Fan, Analyst, Studio and Audio description; clubs, players, language and a chosen metric.
- **Broadcast:** timed overlay contract, producer review, CasparCG/SPX graphics template and evidence export.
- **Experiments:** counterfactual simulations, synthetic video auto-eventing, personal 3D highlights and a phone second screen.
- **Integration:** A2A endpoint, nine MCP tools, Event Hubs and Functions-generated packages.

The video detector has measured limitations: see [evaluation](docs/EVAL.md). Audio description
is implemented; accessibility and usability with real participants remain to be validated.

</details>

## Deploy to Azure

Requires Azure CLI, Azure Developer CLI, a subscription with model quota, and permissions
to create resources and role assignments. Deployment creates billable resources.

```bash
azd auth login
azd env new touchline-demo
azd up
```

Bicep provisions Container Apps, Foundry, managed identity, monitoring, Event Hubs, Functions
and Blob Storage. Agent publication is a required provisioning hook: missing configuration
or missing agent versions fails the command. Deployment configuration supports Microsoft
Entra ID producer roles; see [governance](docs/GOVERNANCE.md).

After deployment, test a real hosted agent request and save the observed result:

```bash
python scripts/smoke_deployment.py https://YOUR_APP --output evidence/cloud-smoke.json
```

The command makes a billable model request. It rejects offline/router answers and fallback
execution. To verify the downstream chain for a published, completed synthetic match, add
`--match-id SYN-00221` using the exact match ID returned by your feed. The full procedure,
recovery drill and result requirements are in [DEPLOYMENT_PROOF.md](docs/DEPLOYMENT_PROOF.md).

### Reliability boundaries

- **One warm replica.** Browser sessions remain in memory; scaling out requires shared session state. Judge replays expire after 15 minutes and do not publish broadcast outputs.
- **One active input match on partition 0.** A Blob journal stores current match history and the Event Hubs resume offset atomically. Restart reconstructs the history without republishing those insights. ETag conflicts stop competing writers. This does not provide distributed ownership or a durable outbound outbox.
- **Outbound retries.** Transient sends retain their event for retry; queue depth, retries and drops are observable. The bounded queue is still process memory and can lose unconfirmed output on abrupt termination.
- **Stable full-time packages.** Events carry the completed package snapshot, so Functions does not depend on a mutable `live` or `demo` session. Duplicate delivery writes the same package key. Teams notifications remain best-effort and may repeat.
- **Isolated failure drills.** A model-outage drill affects its own match, without disabling other viewers' model access. Failed input ingestion reports degraded health and fails the readiness probe.
- **Protected shared playback.** Anonymous viewers can run their own Judge Mode. Shared production controls require the configured producer role; without Entra, deployed shared controls stay read-only.

## Run the checks

```bash
pip install -r functions/requirements.txt pytest
pytest -q
python scripts/evaluate.py --matches 12 --gate --json-out docs/evidence.json
python scripts/ablation.py --matches 12
python scripts/compare_agents.py --prepare --limit 12 --output evidence/comparison-inputs.json
```

The comparison preparation is offline. Live Foundry evaluation, additional-language checks,
load/soak testing and human user tests are separate evidence steps, not implied passes.

## Interfaces

| Interface | Entry point |
|---|---|
| Judge replay | `/judge`, `POST /api/judge`; control token belongs to the creating viewer |
| Evidence receipt | `GET /api/matches/{session}/insights/{id}/receipt?persona=analyst&lang=en` |
| Match data | `/api/matches/{session}` with `/insights`, `/recap`, `/players`, `/audit`, `/dataset.jsonl` |
| Streaming | `/api/matches/{session}/stream` (SSE); `/overlay` for timed graphics |
| Analyst | `POST /api/matches/{session}/ask` with per-request execution provenance |
| Downstream output | `/api/downstream`, `/api/matches/{session}/package` |
| Agent integration | `/.well-known/agent-card.json`, `/a2a`, `/mcp` |

## Documentation

| Document | Purpose |
|---|---|
| [Category case and gap register](docs/WINNING_CASE.md) | Evidence, next steps and limits for every prize |
| [Deployment proof](docs/DEPLOYMENT_PROOF.md) | Capture live Foundry, integration and recovery evidence |
| [Agent comparison](docs/AGENT_COMPARISON.md) | Baselines, fairness and scoring limits |
| [Submission and video](docs/SUBMISSION.md) | Focused project pitch and a sub-two-minute demo |
| [Evaluation](docs/EVAL.md) · [Ablation](docs/ABLATION.md) · [Load](docs/LOADTEST.md) | Measured results with scope |
| [Foundry](docs/FOUNDRY.md) · [Governance](docs/GOVERNANCE.md) | Agent management, controls and limitations |
| [Broadcasters](docs/BROADCASTERS.md) · [Overlay contract](docs/OVERLAY_CONTRACT.md) | Integration and adoption |
| [Impact](docs/IMPACT.md) · [User test](docs/USER_TEST.md) | Pilot goals and human validation protocol |
| [Model card](docs/MODEL_CARD.md) · [Design](docs/DESIGN.md) | Synthetic models and design system |

Licensed under [MIT](LICENSE). Third-party assets retain their documented licenses. This is
an independent hackathon entry; no prize, endorsement or production certification is claimed.
