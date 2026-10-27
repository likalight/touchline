# Agent comparison: make the baseline honest

**Live-model comparison status: 12 attempts completed; scoring corrected after inspecting outputs.** Existing specialist ablations measure the effects
of removing components. They do not prove that a well-designed single agent performs worse.
Microsoft's [orchestration guidance](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
explicitly recommends starting with the least complexity that reliably meets the need.

## The runnable comparison

```bash
python scripts/compare_agents.py --prepare --limit 12 --output evidence/comparison-inputs.json
# With the chosen Foundry model configured; this makes billable model calls:
python scripts/compare_agents.py --run --input evidence/comparison-inputs.json --output evidence/comparison-results.json
```

Preparation runs held-out seeds beginning at 5000 and freezes selected goal/card/milestone
inputs. The two paths receive the same interpreted frames and time-bounded source facts:

The [prepared 12-case dataset](evidence/comparison-inputs.json) remains separate from the
[observed results](evidence/comparison-results.json).
Its SHA-256 binds the cases, scoring context and reference outputs. `--run` reads that
exact dataset, verifies its fingerprint and writes to a separate file. It does not
regenerate or silently replace cases. Retrieving the context tool is required for a
baseline check to pass. Every attempted case, including timeout and malformed output,
stays in the denominator. CI also prepares a fresh dataset as a downloadable artifact.
The 28 October preparation additionally records simulator, model artifact and Python source fingerprints.

- The existing specialist narrators render four audience versions from phrase banks.
- One Agent Framework agent on the configured Foundry model uses a context tool and writes
  all four versions. Its raw output is retained, including malformed or unsupported output.

Both use the same deterministic scoring function for output shape, line limits, supported
numbers/names from **all supplied frames and raw facts**, superlatives and citations. The report preserves inputs, outputs, failures and
request execution provenance. The prompt and limits are versioned in the script. A timeout
or missing model is a failure, not a fabricated successful observation.

## Observed result and scorer correction

| Check | Phrase-bank pipeline | Single model agent |
|---|---:|---:|
| Outputs completed | 12 / 12 | 12 / 12 |
| Format and length contract | 12 / 12 | 2 / 12 |
| Citation membership/required citations | 12 / 12 | 8 / 12 |
| Number/name/superlative evidence membership | 12 / 12 | 11 / 12 |
| All contract checks together | 12 / 12 | 1 / 12 |

**The last row is not factual accuracy or proof of multi-agent superiority.** Most failures
were excessive line/title length; four cases had missing/unsupported citations, and one had an
unsupported numeric token. Semantic associations, tone and usefulness were not scored. A valid
number can still be attached to the wrong meaning; spelled-out numeric words are not comprehensively checked.

The original scorer incorrectly limited the model to selected frame values even though the
prompt supplied richer raw facts. For example, a 7.5-metre shot was available in the source,
but only a rounded 7-metre value was in the selected frame. The original all-contract result
of 0/12 was therefore invalid as a comparison and must not be used to promote the pipeline.

We corrected the scorer **after observing outputs**, applied it identically to both alternatives,
and rescored the same raw outputs with **zero additional model calls**. The
[original report](evidence/comparison-results-before-scorer-fix.json) is retained. The corrected
report preserves original timestamps, raw responses and request execution provenance, and adds
the old/new summary, original report hash and new scorer fingerprint. Reproduce with:

```bash
python scripts/compare_agents.py --rescore --input docs/evidence/comparison-results-before-scorer-fix.json --output evidence/comparison-rescored.json
```

This post-inspection correction is disclosed rather than presented as a preregistered benchmark.
The small purposive sample, one prompt/run and no repair round cannot establish statistical
superiority. A tuned or self-correcting baseline may perform differently. The useful observation
is that the tested phrase banks obey the broadcast-format contract consistently, while this
particular one-shot model baseline needs format/citation repair.

## What it can and cannot establish

This is a **narration strategy comparison**. Both paths benefit from the existing upstream
interpretation. It does not isolate the causal effect of agent count, compare entire systems,
measure semantic equivalence, evaluate perceived usefulness, or establish model cost savings.
Latency of a network model call must not be compared with local phrase rendering as if all
other conditions were equal. A single 12-case sample cannot establish statistical superiority.

Publish every result, including where the single agent does better. Repeat with several fixed
runs and independent human ratings before making a quality claim.

## The stronger end-to-end experiment still needed

Give a capable single agent the same chronological event access and analytics tools, with the
same model, output contract and explicit budget. Let it handle moment selection, match memory,
explanation, personalization and editorial scheduling. Compare it against the full workflow
on held-out matches, preserving equivalent information access and failure injection. Measure
goal coverage, false/unverifiable claims, callback correctness, editorial usefulness, recovery,
end-to-end latency and actual usage. Blind human raters to the system identity.

That experiment is pending. The current ablation, narration runner and recorded handoffs are
useful evidence, but must not be relabeled as this broader experiment.
