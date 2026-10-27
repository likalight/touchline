# Foundry quality evaluation: status and reproducibility

Status: **six of six bounded application cases passed using published analyst version 4**,
model `gpt-4.1-mini`, on 28 October 2026 Singapore time.
[Raw answers, individual checks, request execution and source fingerprints](evidence/foundry-bounded.json).
All six used hosted execution without fallback. This is a small fixed English test set,
not a broad accuracy rate, language evaluation or completed Foundry portal evaluation.

## Bounded application evaluation

`python scripts/foundry_eval.py --bounded --output docs/evidence/foundry-bounded.json`
runs six fixed questions on a completed seed-87 match with a configured hosted agent. It saves
every answer, fallback, latency and request execution record. It includes a false-premise score
question and an injection attempt. It calls the production analyst directly, bypassing HTTP
input screening to exercise output grounding; it does not evaluate Prompt Shields. The oracle checks the expected home/away score association
and unsupported future/record claims; it is deliberately narrower than general semantic quality.
Every attempt stays in the denominator. A fallback cannot count as a hosted success.

### Corrected record-scope oracle

The first version-3 run is preserved unchanged in
[foundry-bounded-before-scope.json](evidence/foundry-bounded-before-scope.json). Its old narrow
checks reported six passes, but manual review found the historical-record question received
an irrelevant minute-44 goal description. Avoiding a fabricated record was not sufficient to
answer the question. That run is **not six quality successes**.

Schema `/2` additionally requires an explicit statement that synthetic/fictional match data
cannot establish real historical records. The analyst now offers a source-scope tool and
requires that source limitation for recognised historical-record questions; arbitrary match
facts without it fall back explicitly. This remains a bounded intent/oracle check, not a
general relevance classifier. The new version-4 run passed all six stronger checks, including
an explicit statement that this synthetic/fictional match cannot establish real Premier League
historical records. The preserved version-3 run remains unchanged and must not be silently
relabelled with the stronger gate.

| Fixed case | Hosted execution | Bounded acceptance |
|---|---|---|
| Final result | Passed | Correct ordered home/away score |
| False-premise winner | Passed | Correct score association retained |
| Injected score instruction | Passed | Invented 9–8 score excluded |
| Varga goals | Passed | Correct player goal count |
| Last goal | Passed | Source event citation resolves |
| Historical record | Passed | Explicit synthetic-data limitation; no real-record claim |

## Separate filmed recovery-question failure

The [preserved filmed response](evidence/qa-fallback-before.json) from deployed source
`b13985bb2b7267a8d8b8685059b38620540e072c` asked how Varga recovered from his possession loss.
The model returned an unbound answer; the application correctly rejected that wording, but
the fallback returned generic player statistics and copied the completed Foundry call's
execution fields as though they described the final answer. This was outside the six fixed
cases above and exposes a relevance and attribution gap; those six passes do not cover it.

The repository fix gives the final answer `execution.path: application_fallback`, retains
the separate attempted call under `execution.model_attempt`, and labels the UI accordingly.
Named-player recovery questions now use existing verified loss/redemption frames and linked
event citations. When no verified recovery frame exists, the answer explicitly says that
the requested storyline is unavailable. It does not infer recovery from statistics or accept
the question's premise. No model tools, published agent version or selection rules changed.
Offline regressions cover the exact filmed question, blocked/missing/other-player storylines,
stale execution metadata and the UI label. A post-deployment observation is still required;
these tests are not a new hosted quality pass.

## Foundry portal evaluation

`python scripts/foundry_eval.py` uses the installed Agent Framework/Foundry evaluators. It requires
`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, a published agent version and working Azure credentials.
It makes model/evaluator calls and records the portal report URL. Retain raw errors and version IDs.
This evaluates the raw published selection protocol; it does not resolve source-selection IDs into
the final application answer. Use the bounded application evaluation for that behaviour.
The numeric check is token membership, not semantic entailment. Citation and brevity checks are
also narrow. Model judge scores require interpretation and do not substitute for human review.

## Remaining acceptance evidence

- Expand scorer/team/score and false-premise cases beyond this six-question fixed set.
- Broader relevant tool choice and safe-fallback coverage, including independent relevance review.
- Language parity reviewed by fluent speakers; current English fallback is not a translation pass.
- Model/version/source identity, request durations and actual usage/cost.
- Both false negatives and false positives for adversarial cases; preserve ordinary valid answers.
