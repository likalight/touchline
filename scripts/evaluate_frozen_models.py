"""Evaluate unchanged model parameters on fresh corrected synthetic matches, without fitting.

python scripts/evaluate_frozen_models.py --matches 30
This checks current-generator calibration; it cannot validate real-match generalisation.
"""
from __future__ import annotations
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evidence_provenance import provenance
from touchline.analytics.models import Logistic, PARAMS_PATH, shot_features, pass_features
from touchline.sim.engine import simulate


def auc(labels, values):
    """Mann-Whitney AUC with average ranks for ties."""
    rows = sorted(zip(values, labels))
    positive = sum(labels)
    if not positive or positive == len(labels):
        return None
    rank_sum = 0.0
    i = 0
    while i < len(rows):
        j = i + 1
        while j < len(rows) and rows[j][0] == rows[i][0]:
            j += 1
        rank_sum += ((i + 1 + j) / 2) * sum(label for _, label in rows[i:j])
        i = j
    return (rank_sum - positive * (positive + 1) / 2) / (positive * (len(labels) - positive))


def metrics(rows):
    probabilities, labels = zip(*rows)
    ordered = sorted(rows)
    calibration = []
    for index in range(5):
        chunk = ordered[index * len(rows)//5:(index+1)*len(rows)//5]
        calibration.append({"n": len(chunk), "predicted": statistics.mean(p for p, _ in chunk),
                            "observed": statistics.mean(y for _, y in chunk)})
    return {"n": len(rows), "auc": auc(labels, probabilities),
            "brier": statistics.mean((p-y)**2 for p, y in rows),
            "base_rate": statistics.mean(labels), "calibration_quintiles": calibration}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7000)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/frozen-models.json")
    args = parser.parse_args()
    if not 5 <= args.matches <= 200:
        parser.error("--matches must be 5..200")
    params = json.loads(PARAMS_PATH.read_text())
    models = {key: Logistic(params[key]["features"], params[key]["weights"], {}) for key in ("xg", "pass")}
    rows = {"xg": [], "pass": []}
    run_provenance = provenance()
    for seed in range(args.seed, args.seed + args.matches):
        _, events = simulate(seed)
        for event in events:
            if event.type == "shot":
                rows["xg"].append((models["xg"].predict(shot_features(event)), int(event.outcome == "goal")))
            elif event.type == "pass" and event.end_x is not None:
                rows["pass"].append((models["pass"].predict(pass_features(event)), int(event.outcome == "complete")))
    result = {"schema": "touchline.frozen-model-evaluation/1", "provenance": run_provenance,
              "seeds": list(range(args.seed, args.seed + args.matches)), "models": {key: metrics(value) for key, value in rows.items()},
              "parameters_changed": False,
              "scope": "Frozen logistic models on corrected synthetic generator; no retraining. Fresh seeds are not the historical holdout, so metric differences do not isolate simulator drift. xT, win probability and real-feed accuracy are not evaluated here."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# Frozen-model evaluation on the current generator", "", f"Observed {run_provenance['generated_at']}; {args.matches} synthetic matches, seeds {args.seed}–{args.seed+args.matches-1}.",
             "", "| Model | Examples | AUC | Brier | Base rate |", "|---|---:|---:|---:|---:|"]
    for key, values in result["models"].items():
        lines.append(f"| {key} | {values['n']} | {values['auc']:.3f} | {values['brier']:.4f} | {values['base_rate']:.3f} |")
    lines += ["", result["scope"], "", "[Raw results, calibration bins and source/model fingerprints](evidence/frozen-models.json).",
              "", "This measures discrimination and calibration; it does not make the model a calibrated real-world probability. Parameters remain unchanged."]
    (ROOT / "docs/FROZEN_MODEL_EVAL.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({key: {k:v for k,v in val.items() if k != "calibration_quintiles"} for key,val in result["models"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
