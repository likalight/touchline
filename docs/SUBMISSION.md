# Submission kit

## Project name
Touchline

## Elevator pitch (project page)

Football graphics today say *what* happened. Touchline explains *why it mattered*: live,
across the whole story of the match, checked number by number, and told differently to
every fan.

**What it is.** An AI insights engine on Azure. It turns a live stream of synthetic football
events into explained moments, storylines, timed broadcast graphics, recaps and a personal
highlights reel for every fan.

**How it works.** A Microsoft Agent Framework workflow runs for every moment:

- An analyst explains it with glass-box models (xG, pass difficulty, expected threat, win probability) trained on our own synthetic league. That includes a counterfactual: "five metres closer, it was a 67% chance".
- A storyline agent with match-long memory adds callbacks: "it began with a loss of possession by Varga", then later "redemption for Varga".
- A fact-checker re-derives every number from the raw events and blocks anything it can't verify, including language-model copy.
- Four narrators work in parallel and write it for a casual fan, an analyst, a studio lower-third and an audio description, in English, Spanish, French and Portuguese, plus any language through Azure OpenAI in Microsoft Foundry.
- A producer turns it into a timed graphics cue that a human can approve.

**What viewers see.**

- **Two views:** the match through a broadcast camera, or a tactical view.
- **Personal controls:** pick your club or both, star favourite players, follow one player all match, or track one metric.
- **Ask the analyst:** fans can question the analyst agent, which also speaks A2A to other agents.
- **My Match:** after the whistle, every fan gets their own highlights reel, rendered with graphics in their language.

**What broadcasters get.**

- **A drop-in graphics template:** it loads in CasparCG and SPX, the open playout tools broadcasters use.
- **An editor-ready edit list:** for the highlights package.
- **A full audit trail:** every graphic and every handoff traced.

**Microsoft and Azure technology.**

- Microsoft Agent Framework: workflows with fan-out and fan-in, agents, and tool calling
- Microsoft Foundry: project, Azure OpenAI deployment, and evaluations
- Azure AI Speech
- A2A protocol
- Azure Container Apps
- Azure Event Hubs
- Azure Monitor and Application Insights through OpenTelemetry
- Managed Identity, Container Registry, and Bicep with `azd`
- GitHub Actions: CI with an evaluation gate

**The problem it solves.** Studios and streamers need graphics that are fast, correct and
relevant to millions of different fans. In our evaluation on 12 unseen matches, Touchline:

- fact-checked 735 of 735 insights, with no broken citations
- explained every goal
- produced each graphic in under 5 ms at p95, inside one broadcast frame
- recovered a faulty feed exactly once

All data is synthetic, and the clubs and players are fictional.

## Category fit

| Brief | Where |
|---|---|
| Ingest | `IngestGuard` (validation, dedupe, re-ordering); sources are the simulator, Event Hubs, or video auto-eventing |
| Interpret | `MatchState`: possession, xG, xT, pass difficulty, PPDA, momentum, control vs chaos, rhythm, win probability, speeds, distances, ratings |
| Explain | `TacticalAnalyst` (drivers, counterfactuals, swings), `StorylineKeeper` (callbacks), `FactChecker` (verification) |
| Render | `touchline.overlay/1` cues, TV camera view, `/overlay`, CasparCG/SPX template |
| Personalise | 4 personas x 4 languages (+ any via Azure OpenAI), favourite clubs (one or both), any number of favourite players, a player-focus mode that follows one player all match, single metric, audio description with neural voice, My Match reels |
| Player identification, pass quality, ball and shot speed | Player tags with sprint threshold, 0-100 pass difficulty, speed records |
| Auto-eventing from video | `touchline/vision`: top-down (pass precision 0.88 / recall 0.75) and broadcast camera (player localisation 0.43 m) |
| Narratives, milestones, recaps | Storylines, brace / hat-trick / saves milestones, story-finding recaps |
| Control vs chaos, pressure changes, rhythm | Phase detector, pressing spells with PPDA, rhythm checks |
| Data innovation | Calibrated simulator, downloadable dataset, model card, demo-seed search |
| Multi-language | Phrase banks in 4 languages; any language via LLM, re-verified |

## Demo video script (under 2:00, no music, no third-party marks)

**Setup.** Record at 1920x1080 on the deployed URL (or locally). The demo match is seed 221.
Open the live app in Fan mode with the TV camera view, speed 10x, and jump to minute 28. The
red card comes at 29'.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00 to 0:08 | TV camera, scorebug, cards streaming | "This is Touchline: AI agents on Azure that explain why football moments matter, live, for every kind of fan." |
| 0:08 to 0:20 | 29' red card lower-third; win probability drops | "Kestrel Bay go down to ten men. Win probability falls, and every number on screen has been checked against the match data." |
| 0:20 to 0:35 | Jump to 36'. Ironmoor goal; the card shows "It began with a loss of possession by Ravi Varga" | "The agents remember. This goal started with Varga giving the ball away, twenty-four seconds earlier." |
| 0:35 to 0:50 | Jump to 75'. Varga equaliser; switch the persona to Analyst to show "Redemption for Ravi Varga: he gave the ball away for their goal in minute 36" | "Forty minutes later, the storyline agent calls back: redemption for Varga." |
| 0:50 to 1:05 | Jump to 93'. The 94' winner banner, hat-trick panel, "down to 2% win probability" | "Down to two percent. Then, in the ninety-fourth minute, a hat-trick." |
| 1:05 to 1:15 | Click an evidence chip: the drawer shows facts, model drivers and the pitch-control map | "Every claim links to the raw events, the factors behind it, and who controlled the pitch at that instant." |
| 1:15 to 1:28 | Switch to Studio, then Audio description (voice plays), then Español | "One moment, four audiences and any language: fan, analyst, studio, and audio description for blind fans." |
| 1:28 to 1:40 | My Match tab: choose Kestrel Bay and follow Varga, then play the rendered reel | "After the whistle, every fan gets their own highlights, cut from the broadcast camera in their language." |
| 1:40 to 1:50 | Agents at work: workflow graph, live handoffs, 735 of 735 verified | "Under the hood: a Microsoft Agent Framework workflow, with every handoff traced and every claim verified." |
| 1:50 to 1:58 | The CasparCG template, then the story page | "And it drops straight into a broadcaster's graphics system. Touchline: the game, explained." |
