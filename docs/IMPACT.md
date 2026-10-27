# Impact hypotheses and how to test them

Updated 28 October 2026. No completed participant study is recorded. We do not yet have
measured producer time savings, viewer comprehension gains, adoption or accessibility outcomes.

| Intended user | Product capability | Hypothesis | Test |
|---|---|---|---|
| Casual football fan | Player story and plain-language explanation | Understand why a goal matters | Ask the viewer to explain the sequence without help; score against source facts |
| Analyst | Source event map, factors and receipts | Inspect a claim faster | Locate the source of a selected claim; compare time/errors with a simple event list |
| Graphics producer | Timed cues and conditional review | Reduce preparation work | Accept/edit/reject equivalent cues against manual preparation; record time and errors |
| Blind or low-vision viewer | Textual evidence, audio-description mode and speech | Make the same information usable | Screen-reader and consenting participant journeys; record missing information and controls |
| Multilingual viewer | Four phrase banks and optional model translation | Preserve meaning across audiences | Fluent-speaker review of entities, scores, negation, time and tone |
| Digital producer | Edit lists and full-time packages | Reduce packaging work | Import a real exported package in the intended tool and measure corrections |

The [user-test kit](user-test-kit.html) and [protocol](USER_TEST.md) are prepared. Participants
are not currently available. Record all attempts, confusion and failures when they are;
do not manufacture quotes or turn population statistics into users served.

## What is measured now

The [pipeline evaluation](EVAL.md) measures deterministic synthetic coverage, implemented
verification, latency and faulty-feed handling. [Cloud proof](DEPLOYMENT_PROOF.md) demonstrates
specific hosted and downstream operations. Neither establishes user benefit or real-feed accuracy.

## Cost and rollout

Actual total deployment cost is not yet measured. Four built-in phrase banks need no language-model
call, but compute and provisioned services still cost resources. Avoid a per-match or “free” claim
until the deployment-specific ledger is recorded; see [BROADCASTERS.md](BROADCASTERS.md).

Start a broadcaster pilot in preview, agree correctness and operator acceptance thresholds,
then consider assisted production. Progress depends on evidence, not a promised calendar date.
