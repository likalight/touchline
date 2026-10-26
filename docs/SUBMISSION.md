# Submission kit

## Project pitch

**Touchline: the game, explained.**

A goal is a moment. The story may have started forty minutes earlier. Touchline turns a
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

1. **Memory:** show the mistake, then the same player's redemption and the late winner.
2. **Personalization with proof:** compare Fan and Analyst, then open and download one receipt.
3. **Purposeful agents:** show an actual failure being caught and a successful hosted request's execution evidence.

The five-stage brief is covered by ingest validation, interpreted match state, causal/contextual
explanations, timed graphics and audience preferences. See the [full category evidence map](WINNING_CASE.md).

## Video storyboard: 1 minute 55 seconds

Record the deployed app after the cloud checks pass. Use only fictional match assets. Use
original narration; avoid copyrighted music and unrelated marks. Trim transitions and rehearse.
The 90-second interactive replay is the exploration path; the edited video can cut between its
chapters while preserving their actual order. Never represent a local run as an Azure run.

| Time | Screen | Suggested narration |
|---|---|---|
| 0:00–0:09 | Start Judge Mode, fictional match visible | “A football graphic tells you what happened. Touchline explains why it mattered—and shows its evidence.” |
| 0:09–0:24 | The mistake and its source event | “This goal began with Varga losing possession. The match memory keeps that connection.” |
| 0:24–0:38 | Redemption chapter; Analyst view | “Forty minutes later, he scores. The agents recognize redemption because they retained the earlier event.” |
| 0:38–0:50 | Winner and hat-trick | “Then the winner. The explanation connects the moment to the whole match.” |
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

## Evidence wording

Use the exact metrics in the latest [evaluation](EVAL.md). State that server pipeline timing
excludes model rewrites, speech and browser delivery. Describe the [ablation](ABLATION.md) as
component-removal experiments, not a complete single-agent comparison. Describe the historical
[load experiment](LOADTEST.md) as a short co-located run, not a capacity guarantee. Report user
study results only after conducting and documenting the sessions.
