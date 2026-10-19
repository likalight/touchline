# Ablation: what each agent is worth

`python scripts/ablation.py --matches 12` switches off one specialist at a time on 12 unseen
synthetic matches (seeds 5000+) and measures what a viewer or broadcaster would suffer. Everything below is
measured, not estimated; the FactChecker row uses deliberately corrupted copy, the kind of mistake a
language model makes, because the deterministic narrators do not make mistakes to catch.

## Summary

| Without | What goes wrong (totals over 12 matches) |
|---|---|
| **IngestGuard** | A 10%-faulty feed applied directly: 786 duplicate events counted twice, 769 events applied out of order, 822 malformed events that would have crashed or corrupted the state; goal count off by 0, pass count off by 453.0, xG off by 1.18. With the guard: 0, 0, 0 and exact. |
| **MomentScout** | Every event becomes a graphic: about **21 graphics a minute** instead of 0.7. Unwatchable. |
| **StorylineKeeper** | 27 callbacks lost, and 20 of 28 goals lose their match context ("it began with a loss of possession by..."). |
| **FactChecker** | Every corrupted line airs. With it, **99.7%** of numeric and name errors are blocked (3483 of 3495), with 0 false alarms on 1808 correct lines. |
| **Producer (editor)** | Studio covering four matches on one graphics output (3 round-ups): a first-come, first-served scheduler airs 85 of 99 big moments (goals, cards, high-value chances) and 45 near-repeats of the same kind of graphic; the editor airs **95 of 99** with 33. The busiest match takes 29% of airtime first-come, 28% with the editor. In a single match moments rarely collide, and both air almost everything (97 vs 89 of 99 big moments): the editor matters when the screen is contested. |

## FactChecker detail

| Corruption | Lines tried | Blocked with FactChecker | Aired without it |
|---|---|---|---|
| changed number | 1156 | 99% | 100% |
| wrong player | 531 | 100% | 100% |
| invented statistic | 1808 | 100% | 100% |
| invented superlative | 1808 | 100% | 100% |

Model copy goes through three checks: every number and name must come from the verified facts, every
rewritten line may only use the numbers of the line it rewrites, and claims like "best ever" or "a club
record" pass only when a verified frame makes them.

## What the ablation found

Running this study exposed four real weaknesses, all fixed and covered by tests:

* correct storyline copy was rejected because the checker ignored names and numbers that come from storyline callbacks (18 false alarms on 463 lines, now 0);
* a fixed list of "structural" numbers (1, 2, 3, 5, 10) let a changed count slip through; window lengths now come from the verified templates;
* a model could swap in a rounding neighbour ("31%" for "32%"); rewrites are now bound line by line to the verified copy;
* invented superlatives were never caught; now they are, unless a verified frame makes the claim.

And it showed where the editor earns its place: on a contested screen, not a quiet one. It now also drops
routine repeats of the same graphic for the same team within 90 seconds.

## Why this needs several agents

One agent asked to do all of this has to hold the whole match, police its own numbers, pick what airs and
write for four audiences in the same breath. Splitting the work gives each job a specialist that can be
measured, tested and replaced on its own, and it is what lets the system check itself: the agent that writes
is never the agent that verifies.
