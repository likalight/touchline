# Foundry quality evaluation: status and reproducibility

Status: **no completed portal quality evaluation is asserted by this document**.
A [hosted smoke request](evidence/hosted-request-20261028.json) succeeded on the earlier
published version. Connectivity and one useful answer do not establish aggregate quality.

## Bounded application evaluation

`python scripts/foundry_eval.py --bounded --output docs/evidence/foundry-bounded.json`
runs six fixed questions on a completed seed-87 match with a configured hosted agent. It saves
every answer, fallback, latency and request execution record. It includes a false-premise score
question and an injection attempt. It calls the production analyst directly, bypassing HTTP
input screening to exercise output grounding; it does not evaluate Prompt Shields. The oracle checks the expected home/away score association
and unsupported future/record claims; it is deliberately narrower than general semantic quality.
Every attempt stays in the denominator. A fallback cannot count as a hosted success.

## Foundry portal evaluation

`python scripts/foundry_eval.py` uses the installed Agent Framework/Foundry evaluators. It requires
`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, a published agent version and working Azure credentials.
It makes model/evaluator calls and records the portal report URL. Retain raw errors and version IDs.
This evaluates the raw published selection protocol; it does not resolve source-selection IDs into
the final application answer. Use the bounded application evaluation for that behaviour.
The numeric check is token membership, not semantic entailment. Citation and brevity checks are
also narrow. Model judge scores require interpretation and do not substitute for human review.

## Remaining acceptance evidence

- Correct scorer/team/score and false-premise handling on held-out examples.
- Relevant tool choice, source-bound output and explicit safe fallback.
- Language parity reviewed by fluent speakers; current English fallback is not a translation pass.
- Model/version/source identity, request durations and actual usage/cost.
- Both false negatives and false positives for adversarial cases; preserve ordinary valid answers.
