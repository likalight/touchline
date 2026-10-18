"""Generate a synthetic league and fit the explainable models on it.

    python scripts/fit_models.py --matches 300

Writes touchline/analytics/params.json and docs/MODEL_CARD.md.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from touchline.analytics.models import (  # noqa: E402
    PASS_FEATURES, PARAMS_PATH, SHOT_FEATURES, XT_NX, XT_NY, Logistic, cell, fx, fy, pass_features, shot_features,
)
from touchline.sim.engine import simulate  # noqa: E402


def auc(y, p):
    pos = [s for s, t in zip(p, y) if t]
    neg = [s for s, t in zip(p, y) if not t]
    if not pos or not neg:
        return float("nan")
    order = sorted([(s, 1) for s in pos] + [(s, 0) for s in neg])
    rank_sum, r = 0.0, 0
    for i, (s, lab) in enumerate(order, 1):
        if lab:
            rank_sum += i
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def brier(y, p):
    return sum((a - b) ** 2 for a, b in zip(p, y)) / len(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=300)
    ap.add_argument("--holdout", type=float, default=0.2)
    args = ap.parse_args()
    t0 = time.time()
    shots, passes, moves = [], [], []
    per_match = []
    for seed in range(1000, 1000 + args.matches):
        meta, evs = simulate(seed)
        g = sum(e.type == "goal" for e in evs)
        per_match.append({"goals": g, "shots": sum(e.type == "shot" for e in evs),
                          "passes": sum(e.type == "pass" for e in evs)})
        for e in evs:
            if e.type == "shot":
                shots.append((seed, shot_features(e), int(e.outcome == "goal"), e))
            elif e.type == "pass" and e.end_x is not None:
                passes.append((seed, pass_features(e), int(e.outcome == "complete")))
                moves.append(e)
            elif e.type in ("carry", "dribble") and e.end_x is not None:
                moves.append(e)
    split = 1000 + int(args.matches * (1 - args.holdout))

    def fit(rows, feats, labels_ok=True):
        tr = [r for r in rows if r[0] < split]
        te = [r for r in rows if r[0] >= split]
        Xtr = [[r[1][k] for k in feats] for r in tr]
        w = Logistic.fit(Xtr, [r[2] for r in tr])
        m = Logistic(feats, w, {})
        ph = [m.predict(r[1]) for r in te]
        yt = [r[2] for r in te]
        base = {k: statistics.mean(r[1][k] for r in tr) for k in feats}
        # calibration by decile
        cal = []
        pairs = sorted(zip(ph, yt))
        n = len(pairs)
        for b in range(5):
            chunk = pairs[b * n // 5:(b + 1) * n // 5]
            if chunk:
                cal.append({"pred": round(statistics.mean(c[0] for c in chunk), 3),
                            "obs": round(statistics.mean(c[1] for c in chunk), 3)})
        return w, base, {"auc": round(auc(yt, ph), 3), "brier": round(brier(yt, ph), 4), "n_train": len(tr),
                         "n_test": len(te), "base_rate": round(statistics.mean(yt), 3), "calibration": cal}

    xg_w, xg_base, xg_eval = fit(shots, SHOT_FEATURES)
    pa_w, pa_base, pa_eval = fit(passes, PASS_FEATURES)

    # ---- expected threat (value iteration) on the attacking frame
    xgm = Logistic(SHOT_FEATURES, xg_w, {})
    shot_n = [[0] * XT_NY for _ in range(XT_NX)]
    goal_x = [[0.0] * XT_NY for _ in range(XT_NX)]
    move_n = [[0] * XT_NY for _ in range(XT_NX)]
    trans: dict[tuple, dict[tuple, int]] = {}
    for _, f, _, e in shots:
        i, j = cell(fx(e.x, e.team), fy(e.y, e.team))
        shot_n[i][j] += 1
        goal_x[i][j] += xgm.predict(f)
    for e in moves:
        i, j = cell(fx(e.x, e.team), fy(e.y, e.team))
        move_n[i][j] += 1
        if e.outcome in ("complete", "success"):
            k = cell(fx(e.end_x, e.team), fy(e.end_y, e.team))
            trans.setdefault((i, j), {}).setdefault(k, 0)
            trans[(i, j)][k] += 1
    xt = [[0.0] * XT_NY for _ in range(XT_NX)]
    for _ in range(40):
        new = [[0.0] * XT_NY for _ in range(XT_NX)]
        for i in range(XT_NX):
            for j in range(XT_NY):
                tot = shot_n[i][j] + move_n[i][j]
                if not tot:
                    continue
                s = shot_n[i][j] / tot
                g = goal_x[i][j] / shot_n[i][j] if shot_n[i][j] else 0.0
                m = move_n[i][j] / tot
                mv = sum(c * xt[k[0]][k[1]] for k, c in trans.get((i, j), {}).items()) / max(move_n[i][j], 1)
                new[i][j] = s * g + m * mv
        xt = new
    xt = [[round(v, 4) for v in row] for row in xt]

    params = {
        "version": "1.0.0",
        "trained_on": f"{args.matches} synthetic matches (seeds 1000-{999 + args.matches})",
        "xg": {"features": SHOT_FEATURES, "weights": xg_w, "baseline": xg_base, "eval": xg_eval},
        "pass": {"features": PASS_FEATURES, "weights": pa_w, "baseline": pa_base, "eval": pa_eval},
        "xt": {"nx": XT_NX, "ny": XT_NY, "grid": xt},
        "league": {
            "goals_per_match": round(statistics.mean(m["goals"] for m in per_match), 2),
            "shots_per_match": round(statistics.mean(m["shots"] for m in per_match), 2),
            "passes_per_match": round(statistics.mean(m["passes"] for m in per_match), 1),
            "pass_completion": round(statistics.mean(r[2] for r in passes), 3),
            "xg_per_shot": round(statistics.mean(xgm.predict(r[1]) for r in shots), 3),
        },
    }
    PARAMS_PATH.write_text(json.dumps(params, indent=1))

    card = ROOT / "docs" / "MODEL_CARD.md"
    card.write_text(f"""# Model card - Touchline explainable models

Trained on **{params['trained_on']}** generated by `touchline/sim/engine.py`; the last
{int(args.holdout * 100)}% of matches are held out for evaluation. No real match data is used.

| Model | Type | Train n | Test n | AUC | Brier | Base rate |
|---|---|---|---|---|---|---|
| xG (shot -> goal) | logistic, {len(SHOT_FEATURES) - 1} features | {xg_eval['n_train']} | {xg_eval['n_test']} | {xg_eval['auc']} | {xg_eval['brier']} | {xg_eval['base_rate']} |
| Pass completion | logistic, {len(PASS_FEATURES) - 1} features | {pa_eval['n_train']} | {pa_eval['n_test']} | {pa_eval['auc']} | {pa_eval['brier']} | {pa_eval['base_rate']} |
| xT | {XT_NX}x{XT_NY} value-iteration grid | {len(moves)} moves, {len(shots)} shots | - | - | - | - |

**Calibration (held-out quintiles, predicted vs observed)**

- xG: {', '.join(f"{c['pred']}->{c['obs']}" for c in xg_eval['calibration'])}
- Pass: {', '.join(f"{c['pred']}->{c['obs']}" for c in pa_eval['calibration'])}

**xG coefficients (log-odds per unit):** {', '.join(f"{k}={w:+.3f}" for k, w in zip(SHOT_FEATURES, xg_w))}

**Pass coefficients:** {', '.join(f"{k}={w:+.3f}" for k, w in zip(PASS_FEATURES, pa_w))}

**Synthetic league profile:** {json.dumps(params['league'])}

Intended use: on-screen explanation of synthetic match events. Glass-box by design: every
prediction is decomposed into feature contributions that the Analyst agent must cite.
Limitations: the simulator's own generative assumptions bound what the models can learn;
the hidden 'true' scoring model also uses player finishing skill, which xG deliberately omits
(so finishing over/under-performance is a real, explainable signal).
""")
    print(json.dumps({"xg": xg_eval, "pass": pa_eval, "league": params["league"], "secs": round(time.time() - t0, 1)}, indent=1))


if __name__ == "__main__":
    main()
