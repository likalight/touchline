# Ablation: component contribution

Observed 2026-10-27T17:20:47.169123+00:00. Git HEAD `103713674de92570c613e9a07460d34d3c101c4a`; dirty working tree: `True`.
Simulator SHA-256: `b7570cd0c19b2b462d85e23a113bcbb31b96d976da8e76ae4d16448967d27695`. Model SHA-256: `e2f64797a51e6362240ea1846a907b97eb16bc0a2d9e82b0bf31077af5eed142`.

`python scripts/ablation.py --matches 12` switches off one specialist at a time on 12 unseen
synthetic matches (seeds 5000+) and measures what a viewer or broadcaster would suffer. Everything below is
measured on this run, not estimated (the list of gaps at the end records what building the study found); the
FactChecker row uses deliberately corrupted copy, the kind of mistake a
language model makes, because the deterministic narrators do not make mistakes to catch.

## Summary

| Without | What goes wrong (totals over 12 matches) |
|---|---|
| **IngestGuard** | A 10%-faulty feed applied directly: 786 duplicate events counted twice, 769 events applied out of order, 822 malformed events that would have crashed or corrupted the state; goal count off by 0, pass count off by 457.0, xG off by 1.18. The same feed through the guard: 0 duplicates, 0 out of order, 822 quarantined, goal count off by 0, pass count off by 0.0. |
| **MomentScout** | Every event becomes a graphic: about **21 graphics a minute** instead of 0.6. Unwatchable. |
| **StorylineKeeper** | 24 callbacks lost, and 20 of 28 goals lose their match context ("it began with a loss of possession by..."). |
| **FactChecker** | Every corrupted line airs. With it, **100.0%** of numeric and name errors are blocked (3483 of 3483), with 0 false alarms on 1801 correct lines. |
| **Producer (editor)** | Studio covering four matches on one graphics output (3 round-ups): a first-come, first-served scheduler airs 84 of 97 big moments (goals, cards, high-value chances) and 45 near-repeats of the same kind of graphic; the editor airs **93 of 97** with 33. The busiest match takes 30% of the graphics aired first-come, 28% with the editor. In a single match moments rarely collide, and both air almost everything (94 vs 88 of 97 big moments): the editor matters when the screen is contested. |

## FactChecker detail

| Corruption | Lines tried | Blocked with FactChecker | Aired without it (by definition) |
|---|---|---|---|
| changed number | 1151 | 1151 / 1151 (100.0%) | 100% |
| wrong player | 531 | 531 / 531 (100.0%) | 100% |
| invented statistic | 1801 | 1801 / 1801 (100.0%) | 100% |
| invented superlative | 1801 | 1801 / 1801 (100.0%) | 100% |

Model copy preserves each verified line's numeric sequence (including multiplicity) and ordered identities. Every
rewritten line is checked separately, and claims like "best ever" or "a club
record" pass only when a verified frame makes them.

The [pre-fix run](evidence/ablation-before-rewrite-binding.json) preserves 13 accepted alterations, including duplicate score values and same-insight player swaps. Conservative binding can reject legitimate language reordering; this is not universal semantic verification.

Uncaught cases: 0. [Raw attempted/caught counts and every uncaught alteration](evidence/ablation-current.json).
The corpus contains actual value changes; formatting-only changes such as 0.0 to 0.00 are not counted as corruptions.

## What the ablation found

Building this study exposed four real weaknesses, all fixed and covered by tests (figures from when they were found):

* correct storyline copy was rejected because the checker ignored names and numbers that come from storyline callbacks (18 false alarms on 463 lines, now 0);
* a fixed list of "structural" numbers (1, 2, 3, 5, 10) let a changed count slip through; window lengths now come from the verified templates;
* a model could swap in a rounding neighbour ("31%" for "32%"); rewrites are now bound line by line to the verified copy;
* invented superlatives were never caught; now they are, unless a verified frame makes the claim.

And it showed where the editor earns its place: on a contested screen, not a quiet one. It now also drops
routine repeats of the same graphic for the same team within 90 seconds.

## What this establishes

Separate components can be tested and replaced independently. This experiment measures removing capabilities,
not the causal effect of agent count. It does not show that a capable single agent with the same tools and budget
would do worse. See AGENT_COMPARISON.md for the bounded narration comparison and remaining end-to-end experiment.
