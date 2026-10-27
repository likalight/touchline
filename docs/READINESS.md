# Readiness: every finding has an explicit disposition

Updated 28 October 2026. “Implemented” below describes repository code, not an automatic
claim about the currently deployed image. [Deployment proof](DEPLOYMENT_PROOF.md) identifies
the observed source/image separately. A 10/10 score or a winning probability is not established.

## Verification checkpoints

- [Final PR9 CI](https://github.com/likalight/touchline/actions/runs/40553039454) passed 152 Python
  tests at `b13985b`, merged as `587a150`. All four jobs passed, including both full browser journeys.
  This is the reviewed code deployed in the current image; later evidence-only edits have their own CI.
- Four required checks (`test`, `browser`, `bicep`, `docker`) now
  gate merges, including administrators. Repository auto-merge is enabled; it is not permission
  to bypass required checks.
- The 12-match pipeline gate verified 730 supported insights and explained all 28 goals,
  with zero citation/template errors. [Raw results](evidence/pipeline-current.json) include scope and fingerprints.
- Six readiness regression tests cover budget recovery, expensive HTTP admission, untrusted
  identity headers, recap corruption, withheld output and role-specific player snapshots.
  The recap corruption test checks score/scorer, aggregates and turning points independently.
- The real judge journey completed all three chapters, receipt downloads, keyboard behaviour
  and responsive layouts at 320, 390 and 768 pixels during this implementation pass.
  This is automated layout/interaction evidence, not a screen-reader or human usability certification.
- [Frozen-model evaluation](FROZEN_MODEL_EVAL.md) uses 30 fresh corrected synthetic matches.
- [External cloud streaming](CLOUD_SOAK.md) delivered all 1,923 ordered source events and the
  correct final score to all 12 attempted clients in one 206.68-second accelerated match.
  This is a bounded external observation, not real-time full-match availability or a capacity ceiling.
- [Ablation](ABLATION.md) preserves actual failures and strict rewrite-binding results.
- [Published analyst version 4](FOUNDRY_EVAL.md) passed all six fixed hosted application cases
  under the strengthened record-scope oracle. Raw results remain available; no portal-quality pass is claimed.

## Audit disposition

The separately [filmed Varga recovery question](evidence/qa-fallback-before.json) exposed a
gap outside the six fixed hosted cases: an unbound model answer fell back to generic stats,
while its completed Foundry attempt was shown as the final answer's execution. The repository
now separates `application_fallback` from nested model-attempt evidence and labels the UI
accurately. Named-player recovery questions render verified loss/redemption frames with
citations, or explicitly report no supported recovery storyline. Offline regression tests
cover the exact question and absent/blocked/other-player stories. Deployment and a new live
answer still need verification; this change is not a new hosted evaluation pass. See
[scope and preserved failure](FOUNDRY_EVAL.md#separate-filmed-recovery-question-failure).

| ID | Audit gap | Current disposition / remaining acceptance |
|---|---|---|
| 01 | Public video and submission confirmation | **Unverified.** Local film exists; accepted-host URL and submission receipt must be confirmed. |
| 02 | Wrong scorer frame accepted | **Implemented and regression-tested:** bind supported frame identities and values to sources; unknown/incomplete types block. |
| 03 | Wrong winner Q&A accepted | **Implemented, regression-tested and bounded hosted check passed:** model selects source-rendered statements; unsupported free prose falls back. Six fixed cases do not establish universal accuracy. |
| 04 | Late event emitted behind current state | **Implemented and regression-tested:** quarantine behind-watermark arrivals; expose late count. This discards late data rather than retroactively correcting state. |
| 05 | Moderation outage treated as safe | **Implemented and regression-tested:** unavailable/malformed Azure results fail closed and are not cached as clean. Offline mode stays explicitly limited. |
| 06 | Contradictory deployment/governance claims | **Updated:** current evidence register, privacy and identity boundaries, historical labels and measured-cost limitation. |
| 07 | Film undersells Microsoft proof | **Remaining:** revise final film to show actual hosted execution/downstream evidence, preserve under-two-minute limit and public upload. |
| 08 | Agent advantage unmeasured | **Bounded comparison measured:** 12 stored model outputs rescored after a disclosed evidence-corpus bug; format/citation results are not semantic accuracy or end-to-end agent superiority. Human comparison remains. |
| 09 | Foundry quality evaluation absent | **Bounded application run measured:** version 4 passed six of six hosted cases, including explicit historical-record scope. Full portal evaluation, broad relevance/language testing and observed rollback remain. |
| 10 | Spotlight misses secondary involvement | **Implemented:** cited participant roles include turnover player and recipient; event time bounds remain explicit. |
| 11 | Main stage inconsistent with opening | **Implemented:** tactical view first, optional stadium, clearer broadcast hierarchy. Human visual preference is unmeasured. |
| 12 | Story and evidence scattered | **Implemented:** compact chapter workspace and progressive disclosure of supporting tools. |
| 13 | Striker card omits goals | **Implemented:** role-specific statistics and hat-trick visibility from delivered snapshots. |
| 14 | Receipt starts with machine details | **Implemented:** human-readable claim/source/check summary; raw evidence retained. |
| 15 | Historical chapter vs current pitch | **Implemented:** explicit selected/live timestamps and source view; chapter selection does not pretend to rewind current state. |
| 16 | Producer UI overstates permissions | **Implemented:** capability-aware controls and honest shared-read-only status. |
| 17 | Enterprise producer identity unproven | **Partly addressed:** untrusted headers ignored; explicit verified-proxy opt-in required. Supported gateway setup and authenticated operator exercise remain. |
| 18 | Outbound queue not durable | **Implemented, locally tested and configured live:** 66 acknowledgements, zero pending/errors after saved-input replay. Acknowledgement-only retries, protected sequential handoff and atomic journal replacement have regressions. Live crash-between-send-and-ack remains untested; consumers deduplicate stable delivery IDs. |
| 19 | Audit/privacy claims too broad | **Partly addressed:** question text removed from application trace notes. Durable editorial retention, deletion and tenant policy remain. |
| 20 | Anonymous work/spend unbounded | **Implemented:** process-local HTTP and model admission/concurrency budgets. Currency cap, per-tenant fairness and distributed limits remain. |
| 21 | Scale/availability unsupported | **Bounded external observation passed:** 12/12 clients received all 1,923 events and correct final score in one 206.68-second accelerated cloud match. One observer machine and deployment; real-time match-length soak, reconnect, capacity ceiling and multi-replica ownership remain. |
| 22 | Model/evaluation provenance stale | **Measured:** fresh frozen logistic-model calibration/discrimination with hashes; updated pipeline/ablation. Real feed, xT and win-probability validation remain. |
| 23 | Recaps lack independent validation | **Implemented and tested:** typed recap claims, score, team aggregates, player summaries and turning points; blocked recaps withheld. |
| 24 | Causal/counterfactual wording | **Updated:** model estimate, baseline-relative effects, explicit absence labels and temporal possession language. Fluent/editor review remains useful. |
| 25 | Language support outruns quality proof | **Partly addressed:** generated previews and English fallback labelled; conservative rewrite checks. Fluent-speaker semantic review remains. |
| 26 | No human benefit evidence | **Remaining:** test kit prepared, participants unavailable. No measured savings, comprehension or adoption claim. |
| 27 | Mobile/accessibility unvalidated | **Partly measured:** automated narrow-view and keyboard journeys passed. Screen reader, low-vision and real-device participant evaluation remain. |
| 28 | CV broadcast accuracy limited | **Scope corrected:** experimental synthetic-camera result, not real broadcast-video accuracy. No inflated CV claim. |
| 29 | Browser journey absent from CI | **Implemented, passed and enforced:** both real journeys with retained screenshots/logs; all four jobs green at `b13985b`, including browser; required checks gate merges/admins. |
| 30 | Strongest cloud proof outside repo | **Published:** current source/image, health/readiness, version-4 hosted source selection, acknowledged outbox outputs, regenerated Functions package and external MCP exchanges. Prior mid-match input recovery remains separately dated. |
| 31 | Total operating cost unknown | **Remaining:** billing query returned incomplete service coverage, so no total or per-match estimate is published. Deployment-wide ledger and judging-period budget remain. |

## Durable delivery scope

`TOUCHLINE_OUTBOX_URL` enables a Blob document with pending messages and acknowledged delivery
IDs. It is optional; the development queue without that variable remains process memory.
The outbox is one writer using conditional ETag updates. It has a finite 10,000-ID ledger
and stops explicitly at capacity. It is not an unlimited production queue.

Sending and acknowledgement are separate commits: a crash between them may redeliver. The
consumer must deduplicate `delivery_id`. Do not claim exactly-once external effects or Teams
notification delivery. The input journal retains one current match, and the new receiver
pauses at the next metadata boundary until processing and durable output acceptance of the
previous match complete. An internal boundary also closes interrupted matches. Metadata/history
replacement commits atomically; a failed replacement preserves prior replay history. Local
handoff and journal tests cover these behaviours. This is sequential handoff, not parallel
multi-match ownership. The [current live observation](DEPLOYMENT_PROOF.md) records 66 durable
acknowledgements after saved-input replay; it does not inject a live crash at the send/ack boundary.

After a successful send, a failed storage acknowledgement is retried without repeatedly sending
again in that process. A crash still permits redelivery. Pending-message age and sender state
now contribute to degraded health (including a 120-second age threshold); recovered transient
errors do not mark health degraded forever. Cross-revision replay and distributed ownership
remain separate concerns.

## Evidence we cannot create with code

Human feedback, fluent-speaker review, authenticated operator acceptance, an accepted public
submission receipt and an actual cost ledger need real observations. They stay visible here;
they are not converted into passing scores by adding more features or tests.
