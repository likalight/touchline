# Submission kit

## Project pitch

**Touchline: the game, explained.**

A goal is a moment. The story may have started much earlier. Touchline turns a
synthetic football feed into explanations that remember the match: the mistake, the
redemption and the winner. Fans get a clear story; analysts get tactical detail; broadcasters
get timed graphics with an editorial decision.

Microsoft Agent Framework coordinates specialist analysis, match memory, independent checks,
four audience narrators and a producer. Microsoft Foundry supplies hosted, tool-grounded Q&A
and model-backed language generation. Azure Container Apps, Event Hubs, Functions and Blob
Storage connect the live experience to downstream packages. Inspect a receipt to see the
facts, original checks, handoffs and audience versions behind a graphic.

**Readiness:** public deployment, live Foundry evidence and participant results must be added
after they are observed. Do not submit claims that these steps have already passed.

## The argument, in three demonstrations

1. **Memory:** show the mistake, then the same player's redemption and the late winner. Click the redemption's earlier-event link: the map returns to the recorded loss of possession.
2. **Personalization with proof:** compare Fan and Analyst, then open and download one receipt.
3. **Purposeful agents:** show an actual failure being caught and a successful hosted request's execution evidence.

Judge Mode now includes **Try an incorrect stat**. It rechecks one chance-quality claim
against the recorded synthetic estimate, changes its value in a copy, and shows the real
checker verdict. The result can be downloaded. Call this a controlled numeric-check
demonstration; it is not a live model outage or evidence of semantic truth.

Four real local pipeline fault drills are recorded in [recovery evidence](evidence/recovery.json).
The application recovered from feed corruption, narrator and storyline failures, and a
fabricated claim. Accelerated local recovery time is not a production latency promise.

The five-stage brief is covered by ingest validation, interpreted match state, causal/contextual
explanations, timed graphics and audience preferences. See the [full category evidence map](WINNING_CASE.md).

## Video storyboard: 1 minute 55 seconds

**Selected video workflow:** use [Brag](https://github.com/latent-spaces/brag), as requested
by the entrant on 27 October. Use the existing storyboard and actual recordings of the
corrected, functioning app as inputs. Keep the final hackathon video under two minutes;
do not substitute Brag's default short launch format for the required demonstration.
Enable narration explicitly (`/brag --voice` in the documented full workflow), retain
readable captions and synthetic-data disclosures, and verify rights for any music used.
Read the current `skills/brag/SKILL.md` and check its prerequisites when video production
starts. This selection records the production plan; Brag has not yet been installed or run.

Record the deployed app after the cloud checks pass. Use only fictional match assets. Use
original narration; avoid copyrighted music and unrelated marks. Trim transitions and rehearse.
The 90-second interactive replay is the exploration path; the edited video can cut between its
chapters while preserving their actual order. Never represent a local run as an Azure run.

| Time | Screen | Suggested narration |
|---|---|---|
| 0:00–0:09 | Start Judge Mode, fictional match visible | “A football graphic tells you what happened. Touchline explains why it mattered—and shows its evidence.” |
| 0:09–0:24 | The mistake and its source event | “This goal began with Varga losing possession. The match memory keeps that connection.” |
| 0:24–0:38 | Redemption chapter; earlier-event link on the evidence map | “Sixteen minutes later, he scores. Follow this connection back to the actual loss of possession. The match has a memory.” |
| 0:38–0:50 | Winner; run the selected goal's alternate ending | “Then the winner. Remove that goal and compare the model's simulated endings. Estimates are labeled separately from match facts.” |
| 0:50–1:07 | Receipt: Fan/Analyst comparison, source facts | “One moment, two audiences. Every receipt shows the facts, checks and agent handoffs behind the graphic.” |
| 1:07–1:22 | A recorded isolated failure drill and recovery | “The specialists have different jobs. When we inject an unsupported number, the checker catches it.” |
| 1:22–1:38 | Actual hosted analyst request and execution proof; corresponding Foundry trace | “Foundry runs the tool-using analyst. This request shows its execution path and the evidence it used.” |
| 1:38–1:48 | Actual downstream package and verified cloud diagram | “The same workflow delivers graphics and a completed match package through Event Hubs, Functions and Blob Storage.” |
| 1:48–1:55 | Product and real demo URL | “Touchline. The game, explained. Explore the story and inspect the proof.” |

If a cloud step has not passed, fix it before recording that claim. Do not replace it with a
staged success, mock service panel or offline result carrying a cloud label.

## Project page links to include

- Public repository and the actual, working Azure demo URL.
- Video under two minutes, tested in an incognito browser.
- Current CI run and its downloadable evaluation artifact.
- One receipt, Foundry evidence and the category case.
- Clear synthetic-data statement, prototype boundaries and dependency licenses.

## Local video rehearsal

`scripts/record_demo.cjs` records actual UI interactions, including the checker test, with
editorial captions. `scripts/render_demo.py` trims waiting between chapters into a video
under two minutes. Every frame is labeled **Local rehearsal / synthetic match**, and the
closing caption lists uncompleted hosted and participant work. The video is silent and
captioned; add original narration and actual hosted footage before the final submission.

```bash
# Use the same Playwright/Chromium environment variables as the browser tests.
DEMO_RECORDING=work/demo-recording node scripts/record_demo.cjs
# Development-only encoder: pip install imageio-ffmpeg==0.6.0
python scripts/render_demo.py --input-dir work/demo-recording --output work/touchline-rehearsal.mp4
```

## Evidence wording

Use the exact metrics in the latest [evaluation](EVAL.md). State that server pipeline timing
excludes model rewrites, speech and browser delivery. Describe the [ablation](ABLATION.md) as
component-removal experiments, not a complete single-agent comparison. Describe the historical
[load experiment](LOADTEST.md) as a short co-located run, not a capacity guarantee. Report user
study results only after conducting and documenting the sessions.


