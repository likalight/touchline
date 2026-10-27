# Deployment evidence runbook

Status: **functional cloud chain verified on 28 October 2026 (Singapore time)**.

- [Live Judge Mode](https://ca-touchline-3a2uvrfhbicqc.livelytree-3fdb8286.southeastasia.azurecontainerapps.io/judge): public readiness passed.
- [Request-level evidence](evidence/cloud-chain.json): hosted Foundry analyst, `gpt-4.1-mini`, completed without fallback and used a scoreboard tool. The numeric/citation checker does not establish semantic entailment.
- Corrected agent versions: analyst **2**, narrator **2**, pinned in the deployment.
- Functions indexed after changing the Event Hubs batch annotation to `typing.List[EventHubEvent]` for the deployed Python 3.11 worker.
- Event Hubs received seed 87 (1,917 events). Functions produced score 3–2, recaps and social-card paths in Blob Storage. The demo and live feed can produce separate packages for the same synthetic match ID.
- The completed live session restored score 3–2 after an application configuration restart. This observation alone does not prove mid-match crash recovery or an exactly-once outbound outbox.
- Original deployed container: CI commit `7914b673e8ddb56b005e2989a75a5762e3b967f9`, digest `sha256:ebd23a1d90a89452eb101395261c8ff4756d0566b14726fea87ef184a3aa4454`.

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
pass. The evaluation checks numbers against tool outputs only; question and answer text are
excluded. Citations must exist in the returned evidence. Save the evaluation report and portal
link. A nonzero exit or a fallback is a failed cloud proof, even if the app remains usable.

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
browser sessions, durable producer audit or transactional outbound outbox. Replay avoids
re-emission but cannot guarantee delivery of a previous process's unconfirmed outbound queue.

## 5. Validate enterprise controls and recovery

- Anonymous shared pause, mode change and cue approval must be rejected.
- A signed-in user without a producer role must be rejected; an authorized producer can review.
- Test an isolated resilience drill and save the corresponding audit output.
- Exercise a transient outbound failure and observe pending, retries and eventual delivery.
- Repeat a full-time input; the canonical package count must not increase for identical data.
- A mismatched or incomplete legacy package must fail instead of storing the next match's data.

Container Apps must be the trusted authentication boundary. Do not expose the raw app port and
trust client-supplied principal headers on the public internet.

## 6. Preserve the submission evidence

Keep a concise evidence directory with cloud smoke JSON, Foundry results, the CI artifact,
a downloaded receipt, restart observations and consented user-study results. Link these from
the project page and replace the README deployment-status paragraph with the verified demo
URL only after these checks pass. Keep the demo available throughout the judging period.
