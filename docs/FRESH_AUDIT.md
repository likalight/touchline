# Fresh judging-readiness audit

28 October 2026. This is a subjective assessment of the evidence available to a reviewer,
not a judge's score, competitor ranking or probability of winning. The deployed checkpoint
is `a69d6af`; newly discovered fixes are local until a later deployment is recorded in
[Deployment proof](DEPLOYMENT_PROOF.md). The [readiness register](READINESS.md) tracks the
original 31 findings and the fresh findings separately.

## What matters for judging

The [official Microsoft rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md)
give each of the five criteria equal weight. Synthetic football-realistic data is required.
A team can receive at most one Grand Prize and one Category Prize. The user will upload the
film; a public accepted-host URL and completed submission remain unconfirmed. This is an
entry gate, independent of the quality of the application.

The strongest argument is **one understandable player story that remains inspectable across
the interface, source events and Azure delivery**. A list of services, agent count, unsupported
impact statistics or a promise to win every category would weaken that argument.

## Five-criterion assessment

The ranges below describe demonstrated readiness on a 10-point editorial scale. They are
deliberately approximate; there is no validated conversion from these ranges to contest odds.

| Criterion | Current evidence-readiness range | Evidence that earns it | What prevents a higher assessment |
|---|---|---|---|
| Technological Implementation | 7–8 | Running Azure deployment; managed identity; event-driven Functions packages; independent checks; 171 Python tests, 11 JS contracts and four green CI jobs at the deployed checkpoint | Fresh NaN/Infinity, session lifecycle and reconnect findings need final integration/deployment; one-writer architecture; incomplete cost evidence |
| Agentic Design & Innovation | 6–7 | Distinct specialist roles, match memory, independent validation, editorial handoffs, MCP exchanges and recorded fault drills | Much of the demonstration is a deterministic workflow; no equivalent-budget end-to-end single-agent comparison; irrelevant but source-bound model answers exposed incomplete intent handling |
| Real-World Impact & Applicability | 5–6 | Concrete fan, analyst and producer workflows; machine-readable cues and packages; a plausible adoption path | No participant/operator results, broadcaster-tool import trial, measured time savings or complete operating budget; human producer identity and durable editorial audit remain unproven |
| User Experience & Presentation | 6–7 before the fresh UI fixes are verified | Coherent 90-second story, receipts, source map, player context, responsive/keyboard journeys and validated 115-second film | New audit found sorting, focus, tour and bootstrap/recovery problems; no first-time user or screen-reader study. Verified fixes could support a 7–8 assessment, but that is not yet observed |
| Adherence to the chosen category | 8–9 for Azure integration | The five-stage brief is represented end to end; cloud services perform observed work; synthetic data, audience views and source inspection are explicit | Category alignment is stronger than production maturity. Capacity, live failure cases and business impact remain bounded or unmeasured |

These rows should not be averaged into a precise contest score. Confidence is higher in
recorded execution/test facts than in aesthetic appeal, usability or impact estimates.

## Category positioning

| Category | Evidence readiness | Strongest pitch | Missing decisive evidence |
|---|---|---|---|
| Best Azure Cloud Native Integration | 8–9; strongest fit | A source-aware fan story produces actual Azure-hosted answers and downstream packages, with restored journal/outbox state and an external streaming observation | Fresh deployment smoke after fixes; a real pending-message failure/recovery experiment; sustainable cost and impact evidence |
| Best Multi-Agent System | 6–7 | Match memory, verification and production specialists have distinct jobs and recover from bounded failures | A well-tuned, equivalent-budget single agent completing the same full task; semantic/usefulness ratings independent of output formatting |
| Best Use of Microsoft Foundry Project | 6–7 | Published, pinned agents invoke source tools; inspectable execution, explicit rejection/fallback and preserved failed cases | Broader relevant answers, demonstrated developer/productivity benefit, language review and a correctly interpreted portal evaluation; six narrow cases do not establish these |
| Best Enterprise Solution | 4–5 | Transparent evidence, managed service identities, input journal, durable output ledger and bounded expensive operations | Verified human producer access, durable editorial audit/retention, per-tenant limits, recovery operations, cost ledger and operator acceptance |
| Grand Prize | Credible complete demonstration; no reliable numeric placing | Show the story, inspect the evidence, then connect the same workflow to actual Microsoft execution | The weakest broad criterion is observed user/business benefit; fresh defects and submission completeness also matter |

The permitted maximum is one Grand Prize plus one category award. Improving every criterion
is useful; claiming all categories are already winnable is not supported.

## Every original finding: priority and disposition

This table groups the original IDs without treating a local fix as deployment proof. The
individual acceptance statements and links remain in [READINESS](READINESS.md#audit-disposition).

| IDs | Current assessment | Next action |
|---|---|---|
| 01 | Submission gate unverified | User uploads the actual 115-second film to an accepted host and completes the project submission; retain confirmation |
| 02, 03, 04, 05 | Original scorer/winner/late-event/moderation defects have targeted fixes | Retain regression evidence; incorporate the separately discovered relevance and non-finite cases before final smoke |
| 06, 30 | Evidence claims corrected and strongest cloud artifacts published | Keep each result tied to its source/image; do not relabel the film or prior soak as a later build |
| 07 | Film refreshed with real hosted and separate downstream evidence | Preserve the actual capture revision and verify the uploaded playback; no need to invent new footage |
| 08, 09 | Narrow comparison and six-case model checks measured | Publish stronger oracle scope; avoid calling format compliance multi-agent superiority or general accuracy |
| 10, 11, 12, 13, 14, 15, 16 | Main experience and permission presentation improved | Finish fresh sorting/tour/focus/bootstrap fixes and repeat real browser journeys |
| 17, 19 | Human identity, durable editorial audit and privacy retention remain incomplete | State the public read-only/isolated boundary; plan a supported authenticated operator pilot, not a last-minute unverified enterprise claim |
| 18, 20, 21 | Durable ledger, process budgets and bounded stream observation exist | Finish expiry/resync validation now; keep live pending-crash recovery, distributed fairness and production capacity as separate work |
| 22, 23, 24, 28 | Fresh frozen-model evidence, checked recaps and bounded model/CV wording exist | Keep synthetic calibration separate from real-feed validity; do not present counterfactual estimates or CV as broadcast ground truth |
| 25, 26, 27 | Fluent-language, participant and accessibility outcomes remain unmeasured | Use the prepared test kit when people are available; automated tests cannot substitute for their feedback |
| 29 | Browser checks run in enforced CI | Require the same four checks for the final code revision and publish its exact result |
| 31 | Complete operating cost still unknown | Record a complete resource/model cost ledger and judging-period budget; partial billing is not a deployment total |

## New findings that can improve the submission now

1. **Answer relevance:** selecting a true source statement can still answer the wrong
   question. The backend audit found minute-for-winner, another-player-for-goals,
   statistics-for-recovery, possession-for-xG and earlier-goal-for-latest-goal cases.
   Local fixes gate recognized English requests by server-assigned topics and identities.
   Validate both correct acceptance and safe rejection; do not imply universal intent coverage.
2. **Finite inputs and claims:** NaN can evade ordinary tolerance comparisons. Local
   event/qualifier and claim preconditions now reject non-finite values. These are input
   integrity fixes, not a substitute for model calibration.
3. **Lifecycle and recovery:** the original SSE contract offered current state plus a
   small replay window, without an event cursor. A long disconnect could lose historical
   continuity, and a full consumer queue silently dropped messages. Test an explicitly
   bounded state-resynchronization/reset contract and expired-session restart; do not
   label it lossless replay or a cloud SLA. Four local tests now cover expiry, long-gap
   snapshots, slow consumers and shared-session replacement. Review of the initial real HTTP
   probe found its expected history window used the returned sequence itself. The corrected
   [local HTTP probe](evidence/reconnect-local.json) passed ten checks using independently
   applied source state, including a deliberately unreplayed 463-event gap and correct
   completed state. The final 20 source events were recovered; the missing history was not.
   External deployment evidence remains pending.
4. **Real interface failures:** fix the hidden tour destination, restore focus/camera on
   exit, make player columns sort correctly from the keyboard, retain focus through refresh,
   remove apparent pre-load probabilities and bound bootstrap requests. Then verify the
   actual browser paths and new recovery status, not just CSS snapshots.
5. **A permissive evaluator:** the old last-goal check only required a valid citation.
   The [corrected source-derived oracle](FOUNDRY_EVAL.md#corrected-last-goal-relevance-oracle)
   rejects earlier-goal identities and malformed/missing explanations. The same six stored
   answers still pass with zero new model calls; the correction is disclosed after inspection.

## What the existing experiments do not prove

The 12-output narration comparison is useful engineering evidence for a fixed broadcast
format. It gives both paths interpreted facts, uses one model prompt with no repair pass and
does not score end-to-end reasoning or human usefulness. Building a credible whole-system
baseline would require a common task, access to the same raw evidence, a fixed token/tool/time
budget, a tuning split separate from evaluation, multiple seeds and blinded assessments.
Do not rush a weak new comparison and advertise it as proof.

The six stored hosted answers pass explicit checks, but the false-premise answer contains
139 words and 15 citations, including unnecessary opposing goals. A source-bound answer can
be correct, verbose and poorly focused simultaneously. The later filmed recovery request
also needed a deterministic fallback. A future relevance suite should include ordinary
questions, adversarial premises, absent information, multi-player comparisons and supported
languages, retaining rejection/fallback rates as well as successful answers.

The external 12-client test covered one accelerated match from one observer. The normal
application update restored acknowledged outputs with no pending messages. Neither establishes
90-minute availability, network-partition behavior, pending-send crash recovery, maximum
capacity or exactly-once effects. Fresh reconnect measurements should state their recovery
contract and preserve missed/duplicate IDs even when the final snapshot is correct.

## Finish order

Finish and test the confirmed correctness/lifecycle/UI fixes; deploy one reviewed image;
repeat bounded hosted relevance, private-output, state-recovery and judge-browser checks;
update the evidence with that exact revision. Then verify the user-uploaded film and final
submission when confirmation is available. Keep language/human studies and enterprise pilots
as visible next steps. Another feature does not compensate for a misleading answer, broken
control, missing submission or unsupported claim.
