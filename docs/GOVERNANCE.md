# Governance, security and operational boundaries

Updated 28 October 2026. Touchline is a synthetic hackathon prototype. This document records
controls and their limits; it is not a security, accessibility or regulatory certification.

## Data and privacy

All match events, players and clubs in the submitted demo are fictional. Fan questions are
free text and may contain personal information. Current application traces omit the question
text; earlier deployments recorded a prefix. An authenticated producer's identity can be
recorded with actions. Do not claim no personal data
is processed. Do not enter private information in the public demo. Retention/deletion policy
and durable tenant separation require a production design and review.

Match state and visitor sessions are process-local. Input match history and consumption offset
are journalled together in Blob Storage. Functions persist synthetic packages and social cards.
Use [deployment proof](DEPLOYMENT_PROOF.md) for the actual observed configuration, not proposed infrastructure.

## Controls and boundaries

| Control | Purpose | Limit |
|---|---|---|
| Deterministic analytics | Calculate source statistics from synthetic events | A model estimate is not a real-world fact or proof of causality |
| FactChecker | Validate supported claim frames and event references | Passing implemented checks is not universal semantic or translation accuracy |
| Q&A grounding | The model selects source-rendered answer IDs; unsupported free-form answers fall back | This bounds accepted wording, not usefulness. Relevance and coverage still need evaluation; English fallback is labelled |
| Content Safety / Prompt Shields | Screen configured model output and incoming questions | Current code rejects malformed/unavailable Azure moderation without caching it as safe; offline/basic screening is not equivalent Azure moderation |
| Foundry Responsible-AI policy | Policy attached to published agent versions | Configuration does not establish zero harmful output |
| Optional Purview middleware | Potential tenant data-policy integration | No deployed Purview enforcement observation is claimed |
| Producer review | Hold non-critical graphics for approval | Goals, red cards and full time can bypass the queue by policy; review is not universal human approval |

The 28 October fixes bind supported frame identities and values, constrain Q&A to source-rendered
statements, quarantine behind-watermark arrivals, and distinguish moderation unavailability.
Recap frames now receive a separate validator and verdict. Use the regression results for
the current revision when assessing remediation. Older
cloud observations predate those fixes and cannot establish that a new version is deployed.
Recaps, commentary, translations and Q&A must be assessed under their own actual paths;
do not claim every surface passes an identical sequence of checks.

## Identity

Fans use anonymous isolated demos. The observed cloud configuration reported `auth=open`,
with shared-control protection. Entra producer authentication is a production requirement,
not an observed feature of that deployment. An app must only trust forwarded identity headers
behind a verified authentication boundary. Setting `TOUCHLINE_AUTH=entra` alone does not create
that boundary, and the existing setup script must be checked against the deployed hosting environment.

Azure services use a user-assigned managed identity. The observed deployment disables local
authentication on supported resources. Managed identity does not authenticate human producers.
Do not expose credentials, token values or subscription details in public evidence.

## Audit and reliability

`/audit` exposes bounded match traces, insight evidence, editorial decisions and drills.
Browser sessions, feedback and producer-action history require separate persistence before
they can form a durable compliance audit. Application Insights configuration is not proof that
every requested trace was observed in the portal.

The prior cloud proof demonstrates one writer recovering input state during a match.
It does not prove exactly-once outbound delivery, zero downtime or a service-level agreement.
An input journal and an output outbox solve different problems. Current code includes an optional
single-writer Blob outbox (`TOUCHLINE_OUTBOX_URL`) with durable pending/acknowledged records;
it is at-least-once, has a finite ledger and requires idempotent downstream effects. The current
deployment reported 66 acknowledgements and zero pending/errors after saved-input replay;
this establishes observed send/ack completion, not crash-between-send-and-ack recovery.
Sequential-match metadata waits for processor completion and durable output acceptance before
replacing the prior input history. Replacement is atomic on storage failure. Acknowledgement-only
retry avoids repeated sends in the same process after a successful transmission, and aged pending
messages/sender failure contribute to degraded health. Local regression tests cover these paths;
live failure injection remains necessary for the recovery claim.
See [delivery scope](READINESS.md#durable-delivery-scope). Current application code adds
bounded expensive public requests and a global model request/concurrency budget. These are
process-local admission controls, not a currency spending cap or distributed rate limit.
The [bounded external stream test](CLOUD_SOAK.md) passed for 12 clients and one accelerated match.
Multi-replica ownership, a sustained real-time match-length soak, reconnect recovery and a
retention/deletion policy remain explicit gates.

## Change management

CI covers Python tests, JS contracts, real browser journeys, deterministic evaluation, Bicep
compilation and container smoke. Published Foundry versions must be tied to source and evaluated
before deployment. Evaluation files record actual source/model fingerprints; historical files
must stay labelled historical. Tests are evidence for covered cases, not proof all bugs are absent.
