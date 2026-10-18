"""Auto-eventing: derive pass and speed metrics from a *video* feed instead of tagging them by hand.

1. `render_frames` turns the synthetic tracking into a 10 fps top-down "tactical cam"
   video (RGB pixels only: pitch, kit colours, a ball, sensor noise, motion between events).
2. `AutoEventer` sees only those pixels. It segments the ball and both kits by colour,
   tracks the 22 players with nearest-neighbour association (initialised once from the
   kick-off line-up, as an operator would), assigns ball ownership, and emits
   passes (passer, receiver, distance, ball speed) and shots (shot speed).
3. `evaluate` matches the detections against the simulator's ground-truth events and
   reports precision / recall / identity accuracy / speed and distance errors.

    python -m touchline.vision.autoevent --seed 7 --from-min 20 --minutes 10 --gif docs/autoevent.gif
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np
from scipy import ndimage

from touchline.schema import PITCH_L, PITCH_W, Event
from touchline.sim.engine import MatchSimulator

PX = 4  # pixels per metre
H, Wd = int(PITCH_W * PX), int(PITCH_L * PX)
FPS = 10
HOME, AWAY, HOME_GK, AWAY_GK = (40, 110, 240), (225, 70, 75), (120, 200, 255), (255, 175, 100)
BALL = (255, 255, 255)


# ------------------------------------------------------------------ rendering
def _pitch() -> np.ndarray:
    img = np.zeros((H, Wd, 3), np.uint8)
    for k in range(10):
        x0, x1 = int(k * Wd / 10), int((k + 1) * Wd / 10)
        img[:, x0:x1] = (32, 92, 60) if k % 2 else (29, 84, 55)
    line = (150, 185, 160)
    img[0, :] = img[-1, :] = img[:, 0] = img[:, -1] = line
    img[:, Wd // 2] = line
    yy, xx = np.ogrid[:H, :Wd]
    r = np.hypot(xx - Wd / 2, yy - H / 2)
    img[np.abs(r - 9.15 * PX) < 0.6] = line
    return img


def _disc(img, x, y, r, col):
    cx, cy = x * PX, (PITCH_W - y) * PX
    x0, x1 = max(0, int(cx - r - 1)), min(Wd, int(cx + r + 2))
    y0, y1 = max(0, int(cy - r - 1)), min(H, int(cy + r + 2))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    m = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    img[y0:y1, x0:x1][m] = col


def ball_at(ev: Event, t: float) -> tuple[float, float]:
    if ev.x is None:
        return None
    if ev.end_x is None:
        return ev.x, ev.y
    q = ev.qualifiers
    spd = (q.get("ball_speed_kmh") or q.get("shot_speed_kmh") or q.get("speed_kmh") or 20) / 3.6
    d = math.hypot(ev.end_x - ev.x, ev.end_y - ev.y)
    dur = max(d / spd, 0.05)
    k = min(1.0, max(0.0, (t - ev.t) / dur))
    return ev.x + (ev.end_x - ev.x) * k, ev.y + (ev.end_y - ev.y) * k


def render_frames(events: list[Event], t0: float, t1: float, noise: float = 6.0, seed: int = 0) -> Iterator[tuple[float, np.ndarray]]:
    rng = np.random.default_rng(seed)
    base = _pitch()
    bank = [rng.normal(0, noise, base.shape).astype(np.int16) for _ in range(16)] if noise else []
    evs = [e for e in events if e.frame is not None]
    i = 0
    t = t0
    while t < t1:
        while i + 1 < len(evs) and evs[i + 1].t <= t:
            i += 1
        a = evs[i]
        b = evs[i + 1] if i + 1 < len(evs) else a
        span = max(b.t - a.t, 1e-6)
        k = min(1.0, max(0.0, (t - a.t) / span))
        img = base.copy()
        for pid, (x0, y0) in a.frame.items():
            x1, y1 = b.frame.get(pid, (x0, y0))
            gk = pid.endswith("1") and len(pid) == 2
            col = (HOME_GK if gk else HOME) if pid[0] == "h" else (AWAY_GK if gk else AWAY)
            _disc(img, x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, 0.95 * PX, col)
        # a shot is logged at the same instant as its save/goal: keep the ball in flight until it arrives
        src = a
        for back in (evs[i - 1] if i else None, a):
            if back is not None and back.type == "shot" and back.end_x is not None:
                q = back.qualifiers
                flight = math.hypot(back.end_x - back.x, back.end_y - back.y) / max(q.get("shot_speed_kmh", 90) / 3.6, 1)
                if back.t <= t < back.t + flight:
                    src = back
        bp = ball_at(src, t)
        if bp:
            _disc(img, bp[0], bp[1], 0.45 * PX, BALL)
        if noise:
            img = np.clip(img.astype(np.int16) + bank[int(rng.integers(len(bank)))], 0, 255).astype(np.uint8)
        yield t, img
        t += 1 / FPS


# ------------------------------------------------------------------ detection
@dataclass
class Detection:
    kind: str
    t: float
    passer: Optional[str]
    receiver: Optional[str]
    team: str
    x: float
    y: float
    end_x: float
    end_y: float
    distance_m: float
    ball_speed_kmh: float


class AutoEventer:
    """Pixels in, events out."""

    def __init__(self, lineup: dict[str, list[float]]):
        self.ids = {"h": [p for p in lineup if p[0] == "h"], "a": [p for p in lineup if p[0] == "a"]}
        self.pos = {p: np.array(v, float) for p, v in lineup.items()}
        self.ball_track: list[tuple[float, Optional[np.ndarray]]] = []
        self.owner_track: list[tuple[float, Optional[str], Optional[np.ndarray]]] = []

    @staticmethod
    def _centroids(mask: np.ndarray, min_px: int = 6) -> list[np.ndarray]:
        lab, n = ndimage.label(mask)
        if n == 0:
            return []
        idx = np.arange(1, n + 1)
        sizes = ndimage.sum(mask, lab, idx)
        cents = ndimage.center_of_mass(mask, lab, idx)
        out = []
        for (cy, cx), s in zip(cents, sizes):
            if s < min_px:
                continue
            # a merged blob of two players: split into two estimates around the centroid
            out.append(np.array([cx / PX, PITCH_W - cy / PX]))
            if s > 2.2 * math.pi * (0.95 * PX) ** 2:
                out.append(np.array([cx / PX, PITCH_W - cy / PX]))
        return out

    def _assign(self, side: str, cents: list[np.ndarray]) -> None:
        ids = list(self.ids[side])
        if not cents:
            return
        pairs = sorted(((np.linalg.norm(self.pos[p] - c), p, j) for p in ids for j, c in enumerate(cents)))
        used_p, used_c = set(), set()
        for d, p, j in pairs:
            if p in used_p or j in used_c or d > 6.0:
                continue
            self.pos[p] = cents[j]
            used_p.add(p)
            used_c.add(j)

    def observe(self, t: float, img: np.ndarray) -> None:
        f = img.astype(np.int16)
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        ball = (r > 215) & (g > 215) & (b > 215)
        home = (b > 170) & (r < 160) & (b - r > 70)
        away = (r > 170) & (g < 150) & (r - g > 70) & (b < 150)
        self._assign("h", self._centroids(home))
        self._assign("a", self._centroids(away))
        bc = self._centroids(ball, min_px=3)
        bpos = bc[0] if bc else None
        if bpos is not None and self.ball_track and self.ball_track[-1][1] is not None and len(bc) > 1:
            prev = self.ball_track[-1][1]
            bpos = min(bc, key=lambda c: np.linalg.norm(c - prev))
        self.ball_track.append((t, bpos))
        owner = None
        if bpos is not None:
            best = min(self.pos, key=lambda p: np.linalg.norm(self.pos[p] - bpos))
            if np.linalg.norm(self.pos[best] - bpos) < 1.4:
                owner = best
        self.owner_track.append((t, owner, bpos))

    def events(self) -> list[Detection]:
        """Ownership segments -> passes / shots with distance and ball speed."""
        out: list[Detection] = []
        segs = []  # (owner, t_start, t_end, pos_start, pos_end)
        for t, o, bp in self.owner_track:
            if o is None:
                continue
            if segs and segs[-1][0] == o and t - segs[-1][2] < 0.35:
                segs[-1][2], segs[-1][4] = t, bp
            else:
                segs.append([o, t, t, bp, bp])
        for (a, _, ta, _, pa), (b, tb, _, pb, _) in zip(segs, segs[1:]):
            if a == b or a[0] != b[0]:
                continue
            d = float(np.linalg.norm(pb - pa))
            flight = max(tb - ta, 1 / FPS)
            if d < 4 or flight > 4.5:
                continue
            spd = self._peak_speed(ta, tb) or d / flight
            out.append(Detection("pass", ta, a, b, "home" if a[0] == "h" else "away", float(pa[0]), float(pa[1]),
                                 float(pb[0]), float(pb[1]), round(d, 1), round(spd * 3.6, 1)))
        # shots: a fast ball arriving at a goal line inside the posts
        tr = [(t, p) for t, p in self.ball_track if p is not None]
        for (t0, p0), (t1, p1) in zip(tr, tr[1:]):
            if (p1[0] > PITCH_L - 2.0 or p1[0] < 2.0) and abs(p1[1] - PITCH_W / 2) < 9.0:
                v = np.linalg.norm(p1 - p0) / max(t1 - t0, 1e-3)
                if v > 9 and (not out or out[-1].kind != "shot" or t1 - out[-1].t > 3):
                    out.append(Detection("shot", t1, None, None, "home" if p1[0] > 50 else "away", float(p0[0]), float(p0[1]),
                                         float(p1[0]), float(p1[1]), 0.0, round(self._peak_speed(t1 - 1.2, t1) * 3.6, 1)))
        return sorted(out, key=lambda d: d.t)

    def _peak_speed(self, ta: float, tb: float) -> float:
        pts = [(t, p) for t, p in self.ball_track if ta - 0.05 <= t <= tb + 0.05 and p is not None]
        sp = [np.linalg.norm(p1 - p0) / max(t1 - t0, 1e-3) for (t0, p0), (t1, p1) in zip(pts, pts[1:])]
        sp = sorted(sp)
        return float(sp[len(sp) // 2]) if sp else 0.0  # median in-flight speed is robust to noise


# ------------------------------------------------------------------ evaluation
def evaluate(seed: int = 7, from_min: float = 20, minutes: float = 10, gif: Optional[str] = None, noise: float = 6.0) -> dict:
    sim = MatchSimulator(seed)
    events = list(sim.run())
    t0, t1 = from_min * 60, (from_min + minutes) * 60
    first = next(e for e in events if e.frame and e.t >= t0)
    ae = AutoEventer({k: list(v) for k, v in first.frame.items()})
    frames = []
    for t, img in render_frames(events, first.t, t1, noise=noise, seed=seed):
        ae.observe(t, img)
        if gif and len(frames) < 200 and t > first.t + 2:
            frames.append(img)
    det = ae.events()
    gt_pass = [e for e in events if e.type == "pass" and e.outcome == "complete" and first.t + 1 <= e.t < t1 - 3]
    gt_shot = [e for e in events if e.type == "shot" and e.outcome in ("goal", "saved", "off_target") and first.t + 1 <= e.t < t1 - 3]
    dp = [d for d in det if d.kind == "pass" and first.t + 1 <= d.t < t1 - 3]
    matched, used, id_ok, spd_err, dist_err = 0, set(), 0, [], []
    for g in gt_pass:
        q = g.qualifiers
        flight = q["distance_m"] / (q["ball_speed_kmh"] / 3.6)
        cands = [(abs(d.t - (g.t + flight * 0.0)), j, d) for j, d in enumerate(dp) if j not in used and d.team == g.team
                 and abs(d.t - g.t) < 1.2]
        if not cands:
            continue
        _, j, d = min(cands, key=lambda c: c[0])
        used.add(j)
        matched += 1
        id_ok += int(d.passer == g.player_id and d.receiver == g.target_id)
        spd_err.append(abs(d.ball_speed_kmh - q["ball_speed_kmh"]))
        dist_err.append(abs(d.distance_m - q["distance_m"]))
    ds = [d for d in det if d.kind == "shot"]
    shot_hits = sum(1 for g in gt_shot if any(abs(d.t - g.t) < 2.5 for d in ds))
    res = {
        "seed": seed, "window_min": [from_min, from_min + minutes], "frames": len(ae.ball_track), "fps": FPS,
        "resolution": f"{Wd}x{H}", "noise_sigma": noise,
        "passes": {"ground_truth": len(gt_pass), "detected": len(dp), "matched": matched,
                   "precision": round(matched / len(dp), 3) if dp else None,
                   "recall": round(matched / len(gt_pass), 3) if gt_pass else None,
                   "passer_and_receiver_correct": round(id_ok / matched, 3) if matched else None,
                   "ball_speed_mae_kmh": round(float(np.mean(spd_err)), 2) if spd_err else None,
                   "distance_mae_m": round(float(np.mean(dist_err)), 2) if dist_err else None},
        "shots": {"ground_truth": len(gt_shot), "detected": len(ds), "recall": round(shot_hits / len(gt_shot), 3) if gt_shot else None},
        "ball_visible": round(sum(1 for _, p in ae.ball_track if p is not None) / max(1, len(ae.ball_track)), 3),
    }
    if gif and frames:
        import imageio.v2 as imageio

        imageio.mimsave(gif, [f[::2, ::2] for f in frames[:120:2]], duration=0.2, loop=0)
    return res


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--from-min", type=float, default=20)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--noise", type=float, default=6.0)
    ap.add_argument("--gif")
    a = ap.parse_args()
    print(json.dumps(evaluate(a.seed, a.from_min, a.minutes, a.gif, a.noise), indent=1))
