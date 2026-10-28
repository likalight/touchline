# Foundry quality evaluation: status and reproducibility

Status: **six of six bounded application cases passed using published analyst version 4**,
model `gpt-4.1-mini`, on 28 October 2026 Singapore time.
[Raw answers, individual checks, request execution and source fingerprints](evidence/foundry-bounded.json).
All six used hosted execution without fallback. This is a small fixed English test set,
not a broad accuracy rate, language evaluation or completed Foundry portal evaluation.

## Latest deployed application checks

On source `706f4f32`, [three actual post-deployment English questions](evidence/audit-deployment.json)
passed bounded final-answer checks. **Only one of the three was an accepted hosted model
selection**: the final-score answer. The false-premise winner and Varga recovery questions
both received irrelevant model selections, which the new topic/identity guard rejected.
The application returned the correct score or verified source story through explicitly
labelled deterministic fallbacks. All three story citations resolved.

These observations validate the application boundary for those questions. They do not turn
the two rejected model selections into model successes or establish a general accuracy rate.
The six-case hosted run below remains tied to its earlier runtime/source and cannot be
combined with these three cases into an undifferentiated success score.

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
| Last goal | Passed | Original run checked citation membership; the separate corrected rescore also checks final-goal identity and explanation context |
| Historical record | Passed | Explicit synthetic-data limitation; no real-record claim |

### Corrected last-goal relevance oracle

The fresh audit found that citation membership alone could accept a description of an earlier
goal for the last-goal question. The stored version-4 answer did identify the correct minute-90
goal, but the test did not enforce that relevance. The original [six-answer report](evidence/foundry-bounded.json)
is preserved unchanged. The [corrected rescore](evidence/foundry-bounded-relevance.json) still
passes six of six using **the same answers and zero new model calls**.

The new oracle derives the last goal's ID, scorer, team and minute directly from the seeded
source events, requires that identity and citation, and checks for an explanation marker.
It also rejects reversed-winner wording alongside a correct score and prevents another
player's separate sentence from supplying the requested goal count. Mutation regressions
include an earlier valid citation, swapped scorer/minute, irrelevant text and missing context.
These explicit English patterns are narrow and can reject legitimate paraphrases; they are
not a general relevance or semantic-accuracy classifier.

This correction was made after inspecting the outputs and is not preregistered. The rescore
retains original execution/provenance, original checks, source-event hash, scorer fingerprint
and original report hash. It refuses to reconstruct the source if the simulator fingerprint
has changed. Reproduce locally without model configuration:

```bash
python scripts/foundry_eval.py --rescore docs/evidence/foundry-bounded.json --output evidence/foundry-bounded-relevance.json
```

The false-premise answer still contains 139 words and 15 citations, including two opposing
goal descriptions. Its correct result does not establish concision or ideal relevance. The
six-case result remains a bounded set of source/identity checks; broader relevance, usefulness
and language quality need independent evaluation.

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
stale execution metadata and the UI label. The [final deployed observation](evidence/final-qa-final-story.json)
on `a69d6af` returned the verified loss/redemption story and three source citations. The model
attempt remained unbound and was rejected; the final answer explicitly reports
`application_fallback`, with that attempt nested separately. This is a successful checked
fallback observation, not a new hosted model-answer quality pass or universal relevance claim.

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
