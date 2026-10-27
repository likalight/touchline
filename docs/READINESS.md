# Readiness: every finding has an explicit disposition

Updated 28 October 2026. “Implemented” below describes repository code, not an automatic
claim about the currently deployed image. [Deployment proof](DEPLOYMENT_PROOF.md) identifies
the observed source/image separately. A 10/10 score or a winning probability is not established.

## Verification checkpoints

- Initial implementation checkpoint: 115 Python tests passed before the durable-outbox addition.
  This is not the final combined suite count; use the final CI run for the submitted revision.
- The 12-match pipeline gate verified 730 supported insights and explained all 28 goals,
  with zero citation/template errors. [Raw results](evidence/pipeline-current.json) include scope and fingerprints.
- Six readiness regression tests cover budget recovery, expensive HTTP admission, untrusted
  identity headers, recap corruption, withheld output and role-specific player snapshots.
  The recap corruption test checks score/scorer, aggregates and turning points independently.
- The real judge journey completed all three chapters, receipt downloads, keyboard behaviour
  and responsive layouts at 320, 390 and 768 pixels during this implementation pass.
  This is automated layout/interaction evidence, not a screen-reader or human usability certification.
- [Frozen-model evaluation](FROZEN_MODEL_EVAL.md) uses 30 fresh corrected synthetic matches.
- [Ablation](ABLATION.md) preserves actual failures and strict rewrite-binding results.

## Audit disposition

| ID | Audit gap | Current disposition / remaining acceptance |
|---|---|---|
| 01 | Public video and submission confirmation | **Unverified.** Local film exists; accepted-host URL and submission receipt must be confirmed. |
| 02 | Wrong scorer frame accepted | **Implemented and regression-tested:** bind supported frame identities and values to sources; unknown/incomplete types block. |
| 03 | Wrong winner Q&A accepted | **Implemented and regression-tested:** model selects source-rendered statements; unsupported free prose falls back. Actual hosted quality run is separate. |
| 04 | Late event emitted behind current state | **Implemented and regression-tested:** quarantine behind-watermark arrivals; expose late count. This discards late data rather than retroactively correcting state. |
| 05 | Moderation outage treated as safe | **Implemented and regression-tested:** unavailable/malformed Azure results fail closed and are not cached as clean. Offline mode stays explicitly limited. |
| 06 | Contradictory deployment/governance claims | **Updated:** current evidence register, privacy and identity boundaries, historical labels and measured-cost limitation. |
| 07 | Film undersells Microsoft proof | **Remaining:** revise final film to show actual hosted execution/downstream evidence, preserve under-two-minute limit and public upload. |
| 08 | Agent advantage unmeasured | **Prepared:** frozen 12-case narration comparison. Live results and equivalent-budget end-to-end/human comparison remain separate. |
| 09 | Foundry quality evaluation absent | **Runnable:** six-call application evaluator and portal protocol runner; no hosted pass until observed results are saved. |
| 10 | Spotlight misses secondary involvement | **Implemented:** cited participant roles include turnover player and recipient; event time bounds remain explicit. |
| 11 | Main stage inconsistent with opening | **Implemented:** tactical view first, optional stadium, clearer broadcast hierarchy. Human visual preference is unmeasured. |
| 12 | Story and evidence scattered | **Implemented:** compact chapter workspace and progressive disclosure of supporting tools. |
| 13 | Striker card omits goals | **Implemented:** role-specific statistics and hat-trick visibility from delivered snapshots. |
| 14 | Receipt starts with machine details | **Implemented:** human-readable claim/source/check summary; raw evidence retained. |
| 15 | Historical chapter vs current pitch | **Implemented:** explicit selected/live timestamps and source view; chapter selection does not pretend to rewind current state. |
| 16 | Producer UI overstates permissions | **Implemented:** capability-aware controls and honest shared-read-only status. |
| 17 | Enterprise producer identity unproven | **Partly addressed:** untrusted headers ignored; explicit verified-proxy opt-in required. Supported gateway setup and authenticated operator exercise remain. |
| 18 | Outbound queue not durable | **Implemented, live validation pending:** optional single-writer Blob outbox commits pending messages before sending and acknowledges afterwards. At-least-once; consumers deduplicate stable delivery IDs. |
| 19 | Audit/privacy claims too broad | **Partly addressed:** question text removed from application trace notes. Durable editorial retention, deletion and tenant policy remain. |
| 20 | Anonymous work/spend unbounded | **Implemented:** process-local HTTP and model admission/concurrency budgets. Currency cap, per-tenant fairness and distributed limits remain. |
| 21 | Scale/availability unsupported | **Remaining:** one writer/replica and one external match. No external match-length cloud soak or multi-replica ownership result. |
| 22 | Model/evaluation provenance stale | **Measured:** fresh frozen logistic-model calibration/discrimination with hashes; updated pipeline/ablation. Real feed, xT and win-probability validation remain. |
| 23 | Recaps lack independent validation | **Implemented and tested:** typed recap claims, score, team aggregates, player summaries and turning points; blocked recaps withheld. |
| 24 | Causal/counterfactual wording | **Updated:** model estimate, baseline-relative effects, explicit absence labels and temporal possession language. Fluent/editor review remains useful. |
| 25 | Language support outruns quality proof | **Partly addressed:** generated previews and English fallback labelled; conservative rewrite checks. Fluent-speaker semantic review remains. |
| 26 | No human benefit evidence | **Remaining:** test kit prepared, participants unavailable. No measured savings, comprehension or adoption claim. |
| 27 | Mobile/accessibility unvalidated | **Partly measured:** automated narrow-view and keyboard journeys passed. Screen reader, low-vision and real-device participant evaluation remain. |
| 28 | CV broadcast accuracy limited | **Scope corrected:** experimental synthetic-camera result, not real broadcast-video accuracy. No inflated CV claim. |
| 29 | Browser journey absent from CI | **Implemented:** both real journeys with retained screenshots/logs. Required branch-protection checks and final CI success are separate repository settings/results. |
| 30 | Strongest cloud proof outside repo | **Published:** dated mid-match recovery, hosted request and downstream JSON, tied to prior source/image. New deployment proof remains necessary. |
| 31 | Total operating cost unknown | **Remaining:** deployment-specific cost ledger and judging-period budget; removed unsupported free/per-match claims. |

## Durable delivery scope

`TOUCHLINE_OUTBOX_URL` enables a Blob document with pending messages and acknowledged delivery
IDs. It is optional; the development queue without that variable remains process memory.
The outbox is one writer using conditional ETag updates. It has a finite 10,000-ID ledger
and stops explicitly at capacity. It is not an unlimited production queue.

Sending and acknowledgement are separate commits: a crash between them may redeliver. The
consumer must deduplicate `delivery_id`. Do not claim exactly-once external effects or Teams
notification delivery. The existing input journal retains one current match. Publish the next
external match only after the current match's package and pending deliveries have completed;
multi-match handoff and changed-source replay require a stronger journal/ownership design.

## Evidence we cannot create with code

Human feedback, fluent-speaker review, authenticated operator acceptance, an accepted public
submission receipt and an actual cost ledger need real observations. They stay visible here;
they are not converted into passing scores by adding more features or tests.
