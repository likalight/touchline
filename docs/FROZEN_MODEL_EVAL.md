# Frozen-model evaluation on the current generator

Observed 2026-10-27T17:08:40.270905+00:00; 30 synthetic matches, seeds 7000–7029.

| Model | Examples | AUC | Brier | Base rate |
|---|---:|---:|---:|---:|
| xg | 684 | 0.725 | 0.0922 | 0.113 |
| pass | 33862 | 0.737 | 0.1272 | 0.822 |

Frozen logistic models on corrected synthetic generator; no retraining. Fresh seeds are not the historical holdout, so metric differences do not isolate simulator drift. xT, win probability and real-feed accuracy are not evaluated here.

[Raw results, calibration bins and source/model fingerprints](evidence/frozen-models.json).

This measures discrimination and calibration; it does not make the model a calibrated real-world probability. Parameters remain unchanged.
