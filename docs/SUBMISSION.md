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

**How it works.** A Microsoft Agent Framework workflow runs for every moment, under a supervisor that rebuilds and retries it if a run fails:

- An analyst explains it with glass-box models (xG, pass difficulty, expected threat, win probability) trained on our own synthetic league. That includes a counterfactual: "five metres closer, it was a 67% chance".
- A storyline agent with match-long memory adds callbacks: "it began with a loss of possession by Varga", then later "redemption for Varga".
- A fact-checker re-derives every number from the raw events and blocks anything it can't verify, including language-model copy.
- Four narrators work in parallel and write it for a casual fan, an analyst, a studio lower-third and an audio description, in English, Spanish, French and Portuguese, plus any language through Microsoft Foundry.
- A producer agent acts as the editor. Moments compete for the screen, and it scores each one, then airs it, cuts in, queues it or drops it, with the reason shown. A human producer can approve every graphic.
- A commentary booth turns each key moment into two voices: a lead call and the analyst's verified line, captioned.

**What viewers see.**

- **A 3D broadcast view:** a floodlit stadium, animated players in club kits, goal replays, an isolated player cam, and LED boards carrying the checked insight. A tactical view sits alongside.
- **Personal controls:** pick a club or both, star favourite players, follow one player all match, track one metric, or turn on two-voice commentary.
- **Ask the analyst:** a Foundry agent with match-data tools. Fan questions pass Azure AI Content Safety Prompt Shields first, and the agent also speaks A2A to other agents.
- **My Match:** after the whistle, each fan's own highlights replay in the 3D stadium and record in their browser, with graphics in their language.

**What broadcasters get.**

- **A drop-in graphics template:** it loads in CasparCG and SPX, the open playout tools broadcasters use.
- **An event-driven back office:** every verified insight streams out on Event Hubs. An Azure Function writes social cards and, at full time, a post-match package to Blob Storage.
- **Controls a security team signs off:** Microsoft Entra ID roles on producer tools, Content Safety, managed identity instead of API keys, and a full audit trail of agent hand-offs, editorial decisions and who approved what.
- **Resilience drills:** break the feed, the model, a narrator, the storyline agent, or inject a made-up number, and watch which agent catches it and how fast it recovers.

**Microsoft and Azure technology.**

- Microsoft Agent Framework: workflows with fan-out and fan-in, a supervisor, agents and tool calling
- Microsoft Foundry: agents published to Foundry Agent Service (versioned, with a content policy), model deployment, tracing, and an evaluation script for Foundry's evaluators
- Azure AI Content Safety (Prompt Shields and moderation) and Azure AI Speech (two neural voices per language)
- A2A protocol
- Azure Container Apps, with Microsoft Entra ID authentication
- Azure Event Hubs (in and out), Azure Functions (Flex Consumption) and Blob Storage
- Azure Monitor and Application Insights through OpenTelemetry
- Managed Identity, Container Registry, and Bicep with `azd`
- GitHub Actions: CI with tests and an evaluation gate

**The problem it solves.** Studios and streamers need graphics that are fast, correct and
relevant to millions of different fans. In our evaluation on 12 unseen matches, Touchline:

- fact-checked 735 of 735 insights, with no broken citations
- explained every goal
- produced each graphic in under 5 ms at p95, inside one broadcast frame
- recovered a faulty feed exactly once

The resilience drills also found a real gap during development, ordinals like "99th" slipping past the number check. It is now fixed and tested.

All data is synthetic, and the clubs and players are fictional.

## Category fit

| Brief | Where |
|---|---|
| Ingest | `IngestGuard` (validation, dedupe, re-ordering); sources are the simulator, Event Hubs, or video auto-eventing |
| Interpret | `MatchState`: possession, xG, xT, pass difficulty, PPDA, momentum, control vs chaos, rhythm, win probability, speeds, distances, ratings |
| Explain | `TacticalAnalyst` (drivers, counterfactuals, swings), `StorylineKeeper` (callbacks), `FactChecker` (verification) |
| Render | Editorial Producer agent, `touchline.overlay/1` cues, 3D broadcast view, `/overlay`, CasparCG/SPX template |
| Personalise | 4 personas x 4 languages (+ any via Microsoft Foundry), favourite clubs (one or both), any number of favourite players, a player-focus mode and isolated player cam, single metric, two-voice commentary with captions, audio description, 3D My Match reels |
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
| 0:00 to 0:08 | 3D broadcast view, scorebug, cards streaming | "This is Touchline: AI agents on Azure that explain why football moments matter, live, for every kind of fan." |
| 0:08 to 0:20 | 29' red card lower-third; win probability drops; Commentary on, captions show both voices | "Kestrel Bay go down to ten men. Two voices call it, and every number on screen has been checked against the match data." |
| 0:20 to 0:33 | Jump to 36'. Ironmoor goal; the replay camera orbits; the card shows "It began with a loss of possession by Ravi Varga" | "The agents remember. This goal started with Varga giving the ball away, twenty-four seconds earlier." |
| 0:33 to 0:45 | Jump to 75'. Varga equaliser; switch to Analyst to show "Redemption for Ravi Varga" | "Forty minutes later, the storyline agent calls back: redemption for Varga." |
| 0:45 to 0:55 | Jump to 93'. The 94' winner, the crowd jumps, "down to 2% win probability" | "Down to two percent. Then, in the ninety-fourth minute, a hat-trick." |
| 0:55 to 1:05 | Producer console: Editor's decisions (aired, cut in, queued, dropped, with reasons) | "A producer agent decides what goes on air, and says why. A human can approve every graphic." |
| 1:05 to 1:17 | Switch to Español, then Audio description; Player cam on Varga | "One moment, four audiences and any language, including audio description for blind fans." |
| 1:17 to 1:30 | Agents at work: press "Inject a made-up number" and "Crash a narrator"; the log shows who caught each and the recovery time | "We break it on purpose. The fact-checker blocks a made-up number; a crashed agent is covered and the show goes on." |
| 1:30 to 1:42 | Azure services panel: Foundry hosted agents, Content Safety, Event Hubs, Functions packages | "It runs on Microsoft Foundry Agent Service, Content Safety, Event Hubs and Azure Functions, with no API keys." |
| 1:42 to 1:55 | My Match: the 3D reel plays, then the CasparCG template | "Every fan gets their own highlights, and broadcasters get graphics that drop straight into their playout. Touchline: the game, explained." |
