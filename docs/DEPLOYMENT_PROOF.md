# Deployment proof and runbook

## Current deployed build — 28 October 2026 Singapore time

Source `a69d6af8ad7d67cb99463cefcb4b884380e6307f` is deployed as digest
`sha256:b1c448d98716f3a4cf961cf70450bfeb47bdb56153845c97258bfc202c9b2de6`.
The observation at 02:23 Singapore time (27 October 18:23 UTC) records:

- [Final deployment](evidence/final-deployment.json), [health](evidence/final-health.json) and
  [readiness](evidence/final-ready.json): healthy/ready service after the application update.
- [Final hosted answer](evidence/final-hosted-answer.json): version-4 `gpt-4.1-mini` source
  selection, bound claims and four citations, no fallback, 6,859 ms model execution.
- [Outbox restoration](evidence/final-outbox-restore-observation.json): all 198 previously
  acknowledged delivery IDs restored; zero pending, errors or new sends at the observation.
  This is a normal application-update experiment, not an injected pending-message crash.
- [Final code CI](https://github.com/likalight/touchline/actions/runs/40558254712): 171 Python
  tests, 11 JavaScript contracts and all four required jobs passed at `a69d6af`.
- [Checked player-story fallback](evidence/final-qa-final-story.json): the exact Varga recovery
  question now returns the verified loss/redemption story with three source citations. The
  model attempt was still rejected as unbound; `application_fallback` correctly identifies
  the final answer. This is a useful deterministic fallback, not a hosted model-answer pass.
- [Private-match output boundary](evidence/final-private-output-observation.json): a complete
  isolated seed-8642 match finished 2–3 with its local package available. Shared outbound
  counters stayed at 198 acknowledged IDs and zero new sends/pending. This is one observed
  run alongside regression tests, not a distributed isolation certification.

The update adds truthful Q&A fallback metadata, a bounded checked-player story route and
prevents public-created private matches from publishing to the shared downstream pipeline.
Earlier hosted, streaming and film observations below retain their original source/image;
they are not represented as reruns on this final image. The existing input journal was
restored, so these checks do not establish new Event Hubs ingestion or an availability SLA.

## Prior readiness and filmed build — 28 October 2026 Singapore time

The reviewed source `b13985bb2b7267a8d8b8685059b38620540e072c`, merged as `587a150`,
was deployed as container digest
`sha256:bd19893ca31ef290ec8157981e3e2108fdde148bb826d37290e296bd36b563cd`.
The observation at 01:54 Singapore time (27 October 17:54 UTC) records:

- [Deployment manifest](evidence/readiness-deployment.json), [health](evidence/readiness-health.json)
  and [readiness](evidence/readiness-ready.json): healthy/ready application with configured Blob outbox;
  66 acknowledged outputs, zero pending, zero errors at this observation.
- [Hosted analyst answer](evidence/readiness-hosted-answer.json): published version 4,
  `gpt-4.1-mini`, completed without fallback in 4,726 ms model execution. It selects exact
  source-rendered statements, with bound claims and four goal citations for the 3–1 result.
- [Downstream observation](evidence/readiness-downstream.json) and [downloaded package](evidence/readiness-stored-package.json):
  Functions built a fresh `SYN-00091` package at 17:53:54 UTC from replay of the saved input
  journal. This is a new output observation on that image, **not a freshly ingested match**.
- [External MCP client exchanges](evidence/external-mcp-current.json): six gates passed,
  covering protocol negotiation, discovery, score shape, source-event resolution, recap source
  checks and readiness. This is interoperability evidence for this client and these calls.
- [Final PR9 CI](https://github.com/likalight/touchline/actions/runs/40553039454): 152 Python
  tests passed; test, browser, Bicep and Docker jobs all passed on the reviewed source.
- [Bounded external cloud streaming](CLOUD_SOAK.md): all 12 attempted clients received all
  1,923 source events in order and the correct 1–1 finish for one isolated seed-221 match at
  30× playback, over 206.68 seconds. All clients ran on one external observer machine.
  This separately created match exercised streaming, not downstream delivery or crash recovery.

This proves configured output persistence and observed send/ack completion. It does not test
a live crash between send and acknowledgement, establish exactly-once effects or prove
multi-replica ownership. See [single-writer limits](READINESS.md#durable-delivery-scope).
The health snapshot precedes the separate hosted request; its zero model-call counter is not
the request's execution evidence. Each published JSON includes source/image context and scope.

## Prior input-recovery experiment — 28 October 2026 Singapore time

These observations belong to source `952d7018043ab04ff7d31fbfc007366dc8c92a22`, merged as
`103713674de92570c613e9a07460d34d3c101c4a`, and container digest
`sha256:9dd97e41963e2fae7ba5da308774fffdd38f13829c96b388da65d3e3ea6b86fc`.
They are prior-build evidence, not automatic proof for later changes.

- [Mid-match recovery JSON](evidence/midmatch-recovery-20261028.json): restarted at minute 75
  while seed 91 continued; restored the prefix, received later events and finished with exactly
  the 1,870 input events in the seeded reference, score 3–1. No input duplicates or skipped gaps.
- [Hosted request JSON](evidence/hosted-request-20261028.json): version-2 analyst with
  `gpt-4.1-mini`, hosted execution, tool evidence, no fallback, about 5.8 seconds model duration.
- [Downstream observation](evidence/downstream-20261028.json): Functions produced synthetic
  packages and social-card paths. Earlier seed-87 [chain proof](evidence/cloud-chain.json) remains
  separately dated.
- [Public Judge Mode](https://ca-touchline-3a2uvrfhbicqc.livelytree-3fdb8286.southeastasia.azurecontainerapps.io/judge).

Scope: one real application restart, one writer, one active input match. This does not prove
exactly-once outbound delivery, multi-match scale, an SLA, universal answer correctness or
user benefit. The hosted answer's old grounding scope was numeric/citation checks only.

### Deployment lessons

The student subscription rejects ACR Tasks. CI builds and smoke-tests the image, then exports a short-lived container artifact; the deployer pushes it to the existing ACR with `crane`. No Azure credential is sent to GitHub Actions.

The installed Container Apps CLI dropped the Express environment's registry identity configuration. Applying the registry identity and image digest together with Azure REST API `2026-07-01` succeeded. Preserve the current ingress, environment variables and identity when patching. Do not reprovision the placeholder image over a working deployment.

Foundry accepted publication with an incomplete strict function schema but rejected invocation. Publication now supplies `additionalProperties: false` and requires every declared property. Runtime uses an explicit pinned agent version, or resolves the latest published version. Preserve the published version IDs in deployment evidence.

The remaining runbook below includes stronger experiments and governance setup; those are **not** implied to have passed by this functional deployment.

## 1. Provision and establish the public URL

Install Azure CLI and Azure Developer CLI. Sign in, select the intended subscription, confirm
model quota in the region, then run `azd up`. Its required publication hook must publish both
agents successfully. Configure Entra producer roles before exercising shared editorial controls.
The normal public Judge Mode remains anonymous and isolated.

Save the deployment command result and app URL. Open `/judge` on desktop and phone, start two
independent replays, pause one and verify the other keeps running. Check refresh and restart.

On Windows, ensure the `python` found by the postprovision hook has `pip` and the project
dependencies available. A virtual environment created by `uv` may not include `pip`.
Check `python -m pip --version` before `azd up`. When using portable CLIs, put their
directories on the current process PATH so Azure SDK credentials can find `az`.
`azd config set auth.useAzCliAuth true` lets azd use the same Azure CLI login.

## 2. Prove hosted Foundry execution

```bash
python scripts/smoke_deployment.py https://YOUR_APP --output evidence/cloud-smoke.json
python scripts/foundry_eval.py
```

The smoke check requires a successful hosted answer with actual tool evidence. Its execution
record belongs to that request, so another viewer's aggregate counters cannot create a false
pass. The default evaluator checks numbers against tool outputs and citation membership. The
separate `python scripts/foundry_eval.py --bounded` application test checks six fixed adversarial
cases; its [observed results](FOUNDRY_EVAL.md) are not a completed portal evaluation. Save the
actual report and any portal link separately. A nonzero exit or fallback fails hosted-execution
proof, even if the deterministic app remains usable.

Capture one Foundry trace, the deployed agent version, model deployment and the corresponding
request ID. Demonstrate a language outside EN/ES/FR/PT and ask a fluent speaker to review its
meaning. Numeric checking alone does not validate a translation.

## 3. Prove the event-driven path

Set `TOUCHLINE_EVENTHUB_NAMESPACE` from the provisioned environment. The publisher identity
needs Event Hubs Data Sender. Publish only one active match on partition 0:

```bash
python scripts/publish_feed.py --seed 87 --speed 40
python scripts/smoke_deployment.py https://YOUR_APP --match-id SYN-00087 --output evidence/cloud-chain.json
```

Wait for Functions to finish before running the second command. It makes another hosted model
request and requires the expected match in the downstream package listing. Inspect the actual
Blob package and a social card, including match identity, final score and citations. Save their
URLs or exported synthetic JSON. Record observed delivery time; do not invent an SLA.

## 4. Prove restart recovery

Use a fresh synthetic match and capture its current score, event IDs and input journal offset.
Restart the single Container Apps replica while the publisher continues. After reconnecting,
compare state with the same seeded reference match. Check that prefix events reconstruct once,
that no earlier insights are republished, and that a subsequent goal continues normally.

The journal stores current-match metadata, events and offset in one Blob replacement. It
resumes after the persisted offset and replays the saved prefix first. ETag conflicts fail
closed. The first deployment reads retained history from the start of partition 0; missing
initial metadata stops ingestion rather than guessing a match. Keep Event Hubs retention long
enough for the uncommitted tail to remain available. A storage or receiver failure changes
`/api/health` to `degraded` and `/api/ready` returns 503; inspect logs before restarting.

**Limits:** one writer/replica and one active input match; no distributed ownership, durable
browser sessions or durable producer audit. With `TOUCHLINE_OUTBOX_URL`, replay reconciles
outputs against the durable ledger; without it, historical outputs are suppressed and the
process-memory queue may lose unconfirmed messages. Input and output are separate storage
commits, so the journal/outbox pair is not an atomic cross-service transaction. The new live
observation above covers send/ack completion, not a crash during that boundary.

## 5. Validate enterprise controls and recovery

- Anonymous shared pause, mode change and cue approval must be rejected.
- A signed-in user without a producer role must be rejected; an authorized producer can review.
- Test an isolated resilience drill and save the corresponding audit output.
- Exercise a transient outbound failure and observe pending, retries and eventual delivery.
- Repeat a full-time input; the canonical package count must not increase for identical data.
- A mismatched or incomplete legacy package must fail instead of storing the next match's data.

An independently configured supported identity gateway must be the trusted authentication boundary.
Current code requires `TOUCHLINE_TRUST_AUTH_PROXY=on` before reading principal headers, in addition
to `TOUCHLINE_AUTH=entra`. Do not set that flag without a gateway that removes spoofed headers
and prevents direct access. Do not expose the raw app port and
trust client-supplied principal headers on the public internet.

## 6. Preserve the submission evidence

Keep a concise evidence directory with cloud smoke JSON, Foundry results, the CI artifact,
a downloaded receipt, restart observations and consented user-study results. Link these from
the project page and replace the README deployment-status paragraph with the verified demo
URL only after these checks pass. Keep the demo available throughout the judging period.
