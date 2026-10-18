# Submission kit

## Project name
Touchline

## Elevator pitch (project page)

Football graphics today say *what* happened. Touchline explains *why it mattered*, live, and
the explanation is different for every viewer.

**What it is.** An AI insights engine running on Azure. It turns a live stream of synthetic
football events into explained moments, timed broadcast overlays and automated recaps.

**How it works.** Microsoft Agent Framework runs a workflow for every moment:

- A Moment Scout spots what deserves airtime.
- A Tactical Analyst explains it with glass-box models. These are xG, pass difficulty, expected threat and win probability, all trained on our own synthetic league. It answers "what would have changed it?" with a counterfactual and cites every claim to an event ID.
- A FactChecker re-derives every number from the match data and blocks anything it can't verify, including LLM copy.
- Four Narrators work in parallel and write the same moment for a casual fan, an analyst, a studio lower-third, and an audio description for blind and low-vision fans. They write in English, Spanish, French and Portuguese, plus any language via Azure OpenAI in Microsoft Foundry.
- A Producer turns it into a timed overlay cue. A human can approve each cue first.

**What else it does.**

- **Personalisation:** fans pick a club, follow one player, or track one metric.
- **Ask the analyst:** questions go to an Agent Framework agent with tool-grounded, cited answers. The same agent is exposed to other agents over **A2A**.
- **Auto-eventing:** a computer-vision tracker generates pass and ball-speed data from video pixels.
- **Resilience:** an Ingest Guard repairs corrupt, duplicated and out-of-order feed events exactly once.

**Microsoft and Azure technology.**

- Microsoft Agent Framework: workflows with fan-out and fan-in, agents, and tool calling
- Microsoft Foundry: project, Azure OpenAI model deployment, and evaluations
- A2A protocol
- Azure Container Apps
- Azure Event Hubs
- Azure Monitor and Application Insights through OpenTelemetry
- Managed Identity, Azure Container Registry, and Bicep with `azd`
- GitHub Actions: tests, an evaluation gate and Bicep compilation on every push

**The problem it solves.** Broadcasters and streamers need graphics that are fast, correct and
relevant to millions of different fans. Touchline makes every explanation:

- verifiable: 100% fact-checked across 671 insights in our evaluation
- quick: p95 of 12 ms per moment on the deterministic path
- personal: 16 renders of every moment

All data is synthetic, and the clubs and players are fictional.

## Category fit (the five required stages)

| Stage | Where |
|---|---|
| Ingest | `IngestGuard`: schema validation, dedupe, re-ordering. Inputs are the in-process simulator, an Event Hubs feed, or auto-eventing from video. |
| Interpret | `MatchState`: possession, xG, xT, pass difficulty, PPDA, momentum, control vs chaos, win probability, speeds, distance, records, ratings |
| Explain | `TacticalAnalyst`: model drivers, counterfactuals, win-probability swings, build-up chains, evidence IDs. `FactChecker` verifies all of it. |
| Render | `Producer` emits `touchline.overlay/1` cues on the match clock. Renderers are the live UI and the transparent `/overlay` output. |
| Personalise | 4 personas x 4 languages (plus any language via LLM), favourite club, follow a player, single-metric mode, read-aloud audio description |

## Demo video script (under 2 minutes, no music)

Record at 1920x1080 with the app at `/`. Pre-roll: open the app, set speed to 10x, and use
Jump to 30'.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00 to 0:10 | Live pitch, scorebug, cards streaming in | "This is Touchline: an AI insights engine on Azure that explains why football moments matter, live, for every kind of fan." |
| 0:10 to 0:30 | Wait for or jump to a goal. The banner lower-third appears with the xG bubble and assist arrow. | "A goal. The agents don't just report it. A 38% chance, the biggest factor was distance, five metres closer it was 79%, and it swung win probability from 43% to 75%." |
| 0:30 to 0:45 | Click an evidence chip. The drawer shows facts and model drivers, and the pitch-control map appears. | "Every claim is cited to the raw event. A fact-checker re-derives every number before anything goes on air. Here's who controlled the pitch at that instant." |
| 0:45 to 1:05 | Toggle Fan, Analyst, Studio, then Audio description (speech plays), then Spanish | "One moment, four audiences: casual fan, analyst, studio lower-third, and audio description for blind fans. In any language." |
| 1:05 to 1:20 | My club = Ironmoor, Follow player = the #9, One metric = Top speed | "Pick your club, follow one player through the match, or track a single number you care about." |
| 1:20 to 1:35 | Agents at work tab: topology, live handoffs, latency, verified/blocked counts | "Under the hood it's a Microsoft Agent Framework workflow: analyst, fact-checker, four narrators in parallel, producer. About ten milliseconds per moment, all traced to Application Insights." |
| 1:35 to 1:50 | Producer console in Review mode: approve a graphic. Then the `/overlay` page. | "Producers can approve graphics, and every cue is timed, machine-readable JSON a rendering partner can play in sync." |
| 1:50 to 1:58 | Ask the analyst: "Why did they score?" | "Fans and other agents, over A2A, can just ask. Touchline: the game, explained." |

Stay under 2:00. Keep the club names visible (they are fictional) and use no music.
