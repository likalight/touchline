# The case for Touchline, category by category

Research checked 26 October 2026 against the [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md), [Microsoft's agent orchestration guidance](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns), [Foundry agent evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators), and [Event Hubs checkpoint guidance](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-python-get-started-send).

The rules give equal weight to implementation, agentic innovation, impact, UX/presentation and category fit. An entrant can receive one Grand Prize and one Category Prize. This is our strategy and evidence register, not a prediction of the judges' decision or an assessment of undisclosed competitors.

**Current focus: Grand Prize + Best Multi-Agent System.** The latest pass adds an interactive
numeric-check challenge, recorded four-fault recovery evidence, a fingerprinted narration
comparison dataset, a local captioned video rehearsal workflow and an anonymous observation
form. The recovery and checker demonstrations are measured locally. The comparison has not
made model calls, and the user-test form has no participant results. Azure authentication,
subscription selection and a spending cap are still needed before provisioning.

Evidence: [recovery run](evidence/recovery.json), [frozen comparison inputs](evidence/comparison-inputs.json),
[comparison scope](AGENT_COMPARISON.md), [observation form](user-test-kit.html), [recording workflow](SUBMISSION.md#local-video-rehearsal).

## Every prize has a distinct argument

| Prize | Our argument | Evidence available in this repository | Evidence still needed |
|---|---|---|---|
| Grand Prize, first place | A complete, memorable story from synthetic event to a personalized explanation with inspectable proof | Isolated 90-second Judge Mode; audience comparison; receipts; complete ingest-to-render workflow; evaluation and CI | Public Azure URL, a rehearsed 1:55 video, observed first-time user success |
| Grand Prize, second place | The same overall case; second place is not a separate product strategy | Same evidence | Same gaps |
| Best Multi-Agent System | Specialists have separate responsibilities and their contributions can be measured | Agent Framework handoffs; match-long memory; independent checks; producer decisions; ablation and failure drills | Live demonstration of a recovery; complete the bounded narration baseline and, if time permits, a capable end-to-end single-agent baseline |
| Best Use of Microsoft Foundry | Managed hosted agents add language and tool-grounded Q&A, with observable lifecycle and evaluation | Publication hook; request-specific execution proof; version configuration; corrected tool-only grounding checks; Foundry evaluator runner | Hosted call and trace; saved evaluation result; a fluent-speaker review of an additional language; observed version change/rollback |
| Best Enterprise Solution | A broadcaster can inspect a claim, review what airs, and adopt the system in preview first | Evidence export; producer roles; managed identity infrastructure; isolated demos; snapshot-based packages; documented limitations | Authenticated producer exercise; operator acceptance/editing measurements; real user/accessibility sessions; durable editorial audit and outbound outbox before production |
| Best Azure Cloud Native Integration | The event-driven chain serves a useful broadcast workflow, with explicit recovery semantics | Input Blob journal and resume offset; replay reconstruction; send retry/backpressure; immutable full-time input; stable package keys; Bicep and container CI | Deploy and observe Event Hubs → app → Event Hubs → Functions → Blob; restart during a feed; record delivery latency; external load/soak test |

## What a "10× better" project would mean

It is a target for usefulness and clarity, not a numerical claim about this version. The best gains come from evidence and a smaller path through the product.

| Improvement | Acceptance evidence | State |
|---|---|---|
| Judges find the core story immediately | Start → mistake → redemption → winner, no manual seeking required | Implemented; browser-tested |
| Memory is visible, rather than buried in a feed | Three visited chapters; redemption links directly to earlier source coordinates; latest/selected state stays distinct | Implemented in Match memory; full replay and delayed-response browser checks |
| A viewer can investigate importance | Selected goal opens paired 1,000-run alternate endings, with model limits beside the result | Existing simulation engine surfaced in the judge journey |
| A claim can be inspected and shared | Receipt shows original facts, checks, decisions and audience versions; JSON downloads | Implemented; regression and browser checks |
| Hosted execution cannot be confused with fallback | A concurrent request carries its own execution path, request ID and tool-evidence count | Implemented; concurrency tests; live cloud run pending |
| A question or answer cannot verify itself | Evaluator trusts tool outputs only and rejects fabricated event citations | Implemented; adversarial regression tests |
| Input restart rebuilds the actual match | Journal history and resume offset are committed together; restored events do not republish old insights | Implemented for one partition and one writer; Azure restart drill pending |
| Delayed packaging cannot read the next match | Full-time event carries the completed snapshot; duplicate input has a stable output key | Implemented; snapshot and duplicate-delivery tests |
| Temporary send failure does not silently discard an event | Same event is retried and pending/retry/drop counters are visible | Implemented; transient failure test; abrupt-process-loss durability remains open |
| Quality claims are reproducible | CI artifact includes metrics, gates, timestamp, synthetic seeds and source fingerprint | Implemented; see the latest CI run |
| Human benefit is demonstrated | Observe 3–5 participants, record task completion and time, keep consented notes | Protocol ready; no participant results claimed |
| Deployment claims match reality | Save cloud smoke, Foundry evaluation, downstream and restart evidence | Runbook ready; requires Azure subscription, quota, permissions and budget |

## Highest-value order

1. **Deploy and verify.** First establish hosted execution and the complete downstream chain. A green local build cannot substitute for this.
2. **Rehearse the judge journey.** Show the story, compare two audiences, open one receipt, then show an actual failure recovery. Record the deployed app.
3. **Collect a small honest user sample.** Ask whether people can explain why a moment mattered, switch audiences and locate supporting evidence without help. Report the denominator and observations.
4. **Run the comparison and Foundry evaluation.** Publish all outcomes, including failures. The current baseline isolates narration; it must not be relabeled an end-to-end agent comparison.
5. **Complete the cloud reliability drill.** Save before/after state, input journal offset and package identity. Keep the one-replica and in-memory outbound limitations visible.

## Gaps we will not hide

- Synthetic-only model results do not validate real Premier League performance.
- Numeric/name checks and supported citations do not prove semantic entailment, translation equivalence or factual truth outside the synthetic source.
- The journal is a single-writer recovery mechanism, not distributed session storage. Concurrent matches need partition-aware routing and ownership before scale-out.
- Browser sessions, feedback and producer action logs remain in memory. They are not a durable compliance archive.
- Outbound retry is not a transactional outbox. A process killed before delivery can lose output. Teams delivery is best-effort and can repeat.
- A 30-second co-located load generator does not establish match-length cloud capacity. CPU alone cannot diagnose the cause of delivery lag.
- Human testing, enterprise adoption, live cloud reliability, operating costs and measured productivity gains are not yet validated.

## Why these choices follow the research

Microsoft's orchestration guidance recommends the least complexity that meets the need. Our case therefore rests on measured specialist contributions and failure isolation, not agent count. Foundry's evaluation guidance distinguishes task outcomes from the tool-use process; the evaluation must inspect returned tool evidence. Event Hubs checkpoints record consumption position, while our stateful application also needs match history. The journal deliberately couples those two before resuming.

The sources guide the design. The repository tests and saved run artifacts are the evidence for what this implementation actually does.

## Differentiation from existing products

The [Premier League Companion](https://www.premierleague.com/en/news/4345260/what-is-the-premier-league-companion)
already offers personalized, AI-assisted discovery of football statistics and content.
[WSC Sports Arena](https://wsc-sports.com/platform/) describes AI event analysis and automated,
personalized sports content. Those official product descriptions establish that a chat box,
personalization or automatic highlights alone is not a credible novelty claim.

Our proposed distinction is the **inspectable decision chain for a live story**: the earlier
mistake, a later callback, independent checks, an editorial decision and two audience versions
in one downloadable receipt. That is a positioning choice supported by our implementation,
not a claim that competitors lack comparable capabilities. The stronger evidence would be
observed producer trust, lower correction/editing effort and a clearer fan understanding.
The project has not been benchmarked against those commercial products.

See [experience research and remaining gaps](EXPERIENCE_RESEARCH.md) for the source-backed
design rationale, the changes shipped, and the remaining evidence priorities.
