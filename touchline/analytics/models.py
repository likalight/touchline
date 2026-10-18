"""Explainable football models, fitted on our own synthetic league (scripts/fit_models.py).

* xG          - logistic regression on shot geometry and context
* Pass model  - logistic P(complete); difficulty = 1 - P(complete)
* xT          - expected-threat grid (Singh, 2018) by value iteration on synthetic moves

All three are glass-box: every prediction can be decomposed into per-feature
contributions, which is what the Analyst agent cites when it explains a moment.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from touchline.schema import PITCH_L, PITCH_W, Event

PARAMS_PATH = Path(__file__).with_name("params.json")
GOAL_Y = PITCH_W / 2
XT_NX, XT_NY = 16, 12

SHOT_FEATURES = ["bias", "distance_m", "angle_rad", "header", "under_pressure", "assisted", "blockers"]
PASS_FEATURES = ["bias", "distance_m", "start_fx", "progress_m", "lofted", "passer_pressure", "receiver_space",
                 "crowd_at_target", "through", "into_box"]

SHOT_LABELS = {
    "distance_m": "distance to goal", "angle_rad": "shooting angle", "header": "header",
    "under_pressure": "defender pressure", "assisted": "through-ball/cross service", "blockers": "bodies in the shot lane",
}
PASS_LABELS = {
    "distance_m": "pass length", "start_fx": "starting position", "progress_m": "forward progress",
    "lofted": "lofted delivery", "passer_pressure": "pressure on the passer", "receiver_space": "space around the receiver",
    "crowd_at_target": "defenders around the target", "through": "through-ball", "into_box": "delivery into the box",
}


def fx(x: float, side: str) -> float:
    return x if side == "home" else PITCH_L - x


def fy(y: float, side: str) -> float:
    return y if side == "home" else PITCH_W - y


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def shot_angle(x: float, y: float) -> float:
    """Angle subtended by the goal mouth, in the attacking frame (goal at x=105)."""
    a1 = math.atan2(GOAL_Y - 3.66 - y, PITCH_L - x)
    a2 = math.atan2(GOAL_Y + 3.66 - y, PITCH_L - x)
    return abs(a1 - a2)


def nearest(frame: Optional[dict], pt, side_prefix: str, exclude: str = "") -> float:
    if not frame:
        return 6.0
    best = 99.0
    for pid, (x, y) in frame.items():
        if pid[0] == side_prefix and pid != exclude:
            best = min(best, math.hypot(x - pt[0], y - pt[1]))
    return best


def count_near(frame: Optional[dict], pt, side_prefix: str, r: float) -> int:
    if not frame:
        return 0
    return sum(1 for pid, (x, y) in frame.items() if pid[0] == side_prefix and math.hypot(x - pt[0], y - pt[1]) < r)


def opponents_bypassed(ev: Event) -> int:
    """How many opponents (excluding the GK) sit between the start and end x of a move."""
    if not ev.frame or ev.end_x is None:
        return 0
    side = ev.team
    opp = "a" if side == "home" else "h"
    s, e = fx(ev.x, side), fx(ev.end_x, side)
    if e <= s:
        return 0
    return sum(1 for pid, (x, _) in ev.frame.items() if pid[0] == opp and not pid.endswith("1") and s < fx(x, side) < e)


# ---------------------------------------------------------------- feature builders
def shot_features(ev: Event) -> dict[str, float]:
    x, y = fx(ev.x, ev.team), fy(ev.y, ev.team)
    q = ev.qualifiers
    return {
        "bias": 1.0,
        "distance_m": math.hypot(PITCH_L - x, GOAL_Y - y),
        "angle_rad": shot_angle(x, y),
        "header": float(q.get("body_part") == "head"),
        "under_pressure": float(bool(q.get("under_pressure"))),
        "assisted": float(q.get("assisted_by", "none") != "none"),
        "blockers": float(q.get("blockers_in_lane", 0)),
    }


def pass_features(ev: Event) -> dict[str, float]:
    side = ev.team
    opp = "a" if side == "home" else "h"
    sx, ex = fx(ev.x, side), fx(ev.end_x, side)
    q = ev.qualifiers
    d = q.get("distance_m") or math.hypot(ev.end_x - ev.x, ev.end_y - ev.y)
    # Space around the *intended* receiver at the moment of the pass (from the tracking frame)
    rcv = ev.frame.get(ev.target_id) if (ev.frame and ev.target_id) else None
    rpt = rcv if rcv else (ev.end_x, ev.end_y)
    efy = fy(ev.end_y, side)
    return {
        "bias": 1.0,
        "distance_m": d,
        "start_fx": sx / PITCH_L,
        "progress_m": ex - sx,
        "lofted": float(q.get("height") == "high"),
        "passer_pressure": float(nearest(ev.frame, (ev.x, ev.y), opp) < 2.5),
        "receiver_space": min(nearest(ev.frame, rpt, opp), 8.0),
        "crowd_at_target": float(count_near(ev.frame, rpt, opp, 6.0) >= 2),
        "through": float(q.get("pass_type") == "through"),
        "into_box": float(ex > 88.5 and 13.8 < efy < 54.2),
    }


# ---------------------------------------------------------------- logistic models
class Logistic:
    def __init__(self, features: list[str], weights: list[float], labels: dict[str, str]):
        self.features, self.w, self.labels = features, weights, labels

    def predict(self, f: dict[str, float]) -> float:
        return _sigmoid(sum(w * f[k] for k, w in zip(self.features, self.w)))

    def explain(self, f: dict[str, float], baseline: dict[str, float]) -> list[dict]:
        """Per-feature contribution in log-odds versus a 'typical' baseline input."""
        out = []
        for k, w in zip(self.features, self.w):
            if k == "bias":
                continue
            delta = w * (f[k] - baseline.get(k, 0.0))
            if abs(delta) > 0.05:
                out.append({"feature": k, "label": self.labels.get(k, k), "value": round(f[k], 2),
                            "logodds": round(delta, 2)})
        return sorted(out, key=lambda r: -abs(r["logodds"]))

    @staticmethod
    def fit(X: list[list[float]], y: list[int], l2: float = 1e-3, iters: int = 60) -> list[float]:
        import numpy as np

        A = np.asarray(X, dtype=float)
        t = np.asarray(y, dtype=float)
        mu, sd = A[:, 1:].mean(0), A[:, 1:].std(0) + 1e-9
        Z = A.copy()
        Z[:, 1:] = (A[:, 1:] - mu) / sd
        w = np.zeros(Z.shape[1])
        for _ in range(iters):  # Newton-Raphson / IRLS
            p = 1 / (1 + np.exp(-Z @ w))
            g = Z.T @ (p - t) + l2 * w
            H = (Z.T * (p * (1 - p))) @ Z + l2 * np.eye(len(w))
            w -= np.linalg.solve(H, g)
        # un-standardise
        wr = w.copy()
        wr[1:] = w[1:] / sd
        wr[0] = w[0] - (w[1:] * mu / sd).sum()
        return [float(v) for v in wr]


# ---------------------------------------------------------------- xT grid
def cell(x: float, y: float) -> tuple[int, int]:
    return (min(XT_NX - 1, max(0, int(x / PITCH_L * XT_NX))), min(XT_NY - 1, max(0, int(y / PITCH_W * XT_NY))))


class Models:
    """Loads fitted parameters and exposes explainable predictions."""

    def __init__(self, params: Optional[dict] = None):
        params = params or json.loads(PARAMS_PATH.read_text())
        self.params = params
        self.xg = Logistic(SHOT_FEATURES, params["xg"]["weights"], SHOT_LABELS)
        self.pass_ = Logistic(PASS_FEATURES, params["pass"]["weights"], PASS_LABELS)
        self.xt_grid: list[list[float]] = params["xt"]["grid"]
        self.shot_baseline = params["xg"]["baseline"]
        self.pass_baseline = params["pass"]["baseline"]

    def shot_xg(self, ev: Event) -> tuple[float, dict]:
        f = shot_features(ev)
        return self.xg.predict(f), f

    def pass_complete_prob(self, ev: Event) -> tuple[float, dict]:
        f = pass_features(ev)
        return self.pass_.predict(f), f

    def xt(self, x: float, y: float, side: str) -> float:
        i, j = cell(fx(x, side), fy(y, side))
        return self.xt_grid[i][j]

    def xt_added(self, ev: Event) -> float:
        if ev.end_x is None or ev.team is None:
            return 0.0
        return self.xt(ev.end_x, ev.end_y, ev.team) - self.xt(ev.x, ev.y, ev.team)

    def counterfactual_shot(self, f: dict[str, float]) -> Optional[dict]:
        """'What would have made this a better chance?' - a minimal counterfactual."""
        base = self.xg.predict(f)
        best = None
        for name, change in (("five metres closer", {"distance_m": max(f["distance_m"] - 5, 1)}),
                             ("free of pressure", {"under_pressure": 0.0}),
                             ("struck with the foot", {"header": 0.0}),
                             ("a clear shooting lane", {"blockers": 0.0})):
            g = dict(f)
            g.update(change)
            if g == f:
                continue
            if name == "five metres closer":
                # recompute the angle consistently for a point 5m nearer the goal centre
                g["angle_rad"] = min(f["angle_rad"] * (f["distance_m"] / max(g["distance_m"], 1)), 1.6)
            v = self.xg.predict(g)
            if best is None or v - base > best["delta"]:
                best = {"change": name, "xg_after": round(v, 2), "delta": round(v - base, 2)}
        return best if best and best["delta"] >= 0.03 else None


_MODELS: Optional[Models] = None


def get_models() -> Models:
    global _MODELS
    if _MODELS is None:
        _MODELS = Models()
    return _MODELS
