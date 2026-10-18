"""Auto-eventing from the *broadcast* camera angle.

The detector receives only rendered TV frames plus camera telemetry (where the camera
is pointing, as broadcast camera-tracking systems provide). For every frame it:
  1. segments both kits and the ball by colour,
  2. takes each player's foot point (the bottom of the kit plus leg length, scaled by the
     blob's own size) and maps it onto the pitch by intersecting the camera ray with the
     ground plane (the inverse of the projection used to render),
  3. feeds those pitch positions to the same tracker / ownership / pass logic as the
     top-down auto-eventer.
Players outside the shot keep their last known position, exactly the limitation a real
single-camera system has.

    python -m touchline.vision.broadcast_cv --seed 7 --from-min 20 --minutes 5
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
from scipy import ndimage

from touchline.sim.engine import MatchSimulator
from touchline.vision.autoevent import AutoEventer, evaluate_detections
from touchline.vision.camera import BroadcastRenderer, Camera, Scene


class BroadcastAutoEventer(AutoEventer):
    FLIGHT_SPEED = True
    _last_ball_t = -1e9
    def observe_broadcast(self, t: float, img: np.ndarray, cam: Camera) -> None:
        f = img.astype(np.int16)
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        home = (b > 170) & (r < 160) & (b - r > 70)
        away = (r > 170) & (g < 150) & (r - g > 70) & (b < 150)
        ball = (r > 238) & (g > 238) & (b > 238)
        visible = []
        self.last_feet = {}
        for side, mask in (("h", home), ("a", away)):
            feet = self._feet(mask, cam)
            self.last_feet[side] = feet
            visible += self._assign(side, feet) or []
        # white blobs touching a kit are shirt numbers, not the ball
        kits = ndimage.binary_dilation(home | away, iterations=1)
        ball = ball & ~kits
        lab, n = ndimage.label(ball)
        bpos = None
        if n:
            idx = np.arange(1, n + 1)
            sizes = ndimage.sum(ball, lab, idx)
            cents = ndimage.center_of_mass(ball, lab, idx)
            boxes = ndimage.find_objects(lab)
            cands = []
            for s_, c_, bx in zip(sizes, cents, boxes):
                hh, ww = bx[0].stop - bx[0].start, bx[1].stop - bx[1].start
                round_ = 0.6 <= ww / max(hh, 1) <= 1.7 and s_ >= 0.45 * hh * ww  # a ball, not a goalpost or a line
                if 3 <= s_ <= 400 and round_:
                    cands.append((s_, c_))
            if cands:
                prev = next((p for _, p in reversed(self.ball_track[-30:]) if p is not None), None)
                pts = []
                for s, (cy, cx) in cands:
                    radius = math.sqrt(s / math.pi)
                    gx, gy = cam.to_ground(cx, cy + radius)
                    if not math.isnan(gx):
                        pts.append(np.array([gx, gy]))
                if pts:
                    if prev is not None:
                        cand = min(pts, key=lambda p: np.linalg.norm(p - prev))
                        gap = t - self._last_ball_t
                        # the ball cannot travel faster than ~35 m/s: reject implausible jumps
                        bpos = cand if np.linalg.norm(cand - prev) <= 4 + 35 * gap else None
                    else:
                        bpos = pts[0]
        if bpos is not None:
            self._last_ball_t = t
        self.ball_track.append((t, bpos))
        owner = None
        if bpos is not None and visible:
            # ownership from this frame's detections, not stale tracks of off-screen players
            best = min(visible, key=lambda p: np.linalg.norm(self.pos[p] - bpos))
            if np.linalg.norm(self.pos[best] - bpos) < 2.3:
                owner = best
        self.owner_track.append((t, owner, bpos))

    @staticmethod
    def _feet(mask: np.ndarray, cam: Camera) -> list[np.ndarray]:
        lab, n = ndimage.label(mask)
        if not n:
            return []
        out = []
        for sl, i in zip(ndimage.find_objects(lab), range(1, n + 1)):
            ys, xs = sl
            hpx = ys.stop - ys.start
            if hpx < 3 or (ys.stop - ys.start) * (xs.stop - xs.start) < 6:
                continue
            sub = lab[sl] == i
            cx = xs.start + np.nonzero(sub)[1].mean()
            # shirt is 33% of body height and ends 53% above the feet
            foot_v = ys.stop + hpx * (0.53 / 0.33)
            gx, gy = cam.to_ground(cx, foot_v)
            if not math.isnan(gx) and -8 < gx < 113 and -8 < gy < 76:
                out.append(np.array([gx, gy]))
                if (xs.stop - xs.start) > hpx * 2.6:  # two players side by side
                    out.append(np.array([gx, gy]))
        return out


def evaluate(seed: int = 7, from_min: float = 20, minutes: float = 5, width: int = 960, height: int = 540, noise: float = 5.0) -> dict:
    sim = MatchSimulator(seed)
    events = list(sim.run())
    t0, t1 = from_min * 60, (from_min + minutes) * 60
    first = next(e for e in events if e.frame and e.t >= t0)
    rend = BroadcastRenderer(sim.meta, Camera(width=width, height=height), noise=noise, seed=seed)
    scene = Scene(events)
    ae = BroadcastAutoEventer({k: list(v) for k, v in first.frame.items()})
    cams: list = []
    loc_err: list = []
    ball_err: list = []
    t = first.t
    pl, b, _ = scene.at(t)
    rend.cam.tx, rend.cam.ty = b[0] if b else 52.5, 30.0
    while t < t1:
        pl, b, _ = scene.at(t)
        if b:
            rend.cam.follow(b[0], b[1], 0.07)
        img = np.asarray(rend.frame(pl, b))
        telemetry = Camera(width=width, height=height, tx=rend.cam.tx, ty=rend.cam.ty)  # pan target only
        ae.observe_broadcast(t, img, telemetry)
        cams.append((t, telemetry))
        # localisation accuracy: every detected foot point vs the nearest true player of that team
        for side, feet in ae.last_feet.items():
            truth = [np.array(p) for pid, p in pl.items() if pid[0] == side]
            for ft in feet:
                loc_err.append(float(min(np.linalg.norm(ft - tr) for tr in truth)))
        bp = ae.ball_track[-1][1]
        if bp is not None and b and b[2] < 0.5:
            ball_err.append(float(np.linalg.norm(bp - np.array(b[:2]))))
        t += 0.1
    res = evaluate_detections(ae, events, first.t, t1)
    # recall on passes that happen entirely in shot (a single broadcast camera cannot see the rest)
    import bisect
    ts = [c[0] for c in cams]

    def in_shot(x, y, tt):
        i = min(max(bisect.bisect_left(ts, tt), 0), len(cams) - 1)
        px, z = cams[i][1].project(np.array([[x, y, 0.0]]))
        u, v = px[0]
        return bool(z[0] > 0.5 and 0 <= u < width and 0 <= v < height)

    det = [d for d in ae.events() if d.kind == "pass"]
    gt = [e for e in events if e.type == "pass" and e.outcome == "complete" and first.t + 1 <= e.t < t1 - 3]
    vis = [e for e in gt if in_shot(e.x, e.y, e.t) and in_shot(e.end_x, e.end_y, e.t + e.qualifiers["distance_m"] / (e.qualifiers["ball_speed_kmh"] / 3.6))]
    hit = sum(1 for e in vis if any(abs(d.t - e.t) < 1.2 and d.team == e.team for d in det))
    res["localisation"] = {
        "player_detections": len(loc_err),
        "player_error_m_p50": round(float(np.median(loc_err)), 2), "player_error_m_p90": round(float(np.percentile(loc_err, 90)), 2),
        "ball_on_ground_error_m_p50": round(float(np.median(ball_err)), 2) if ball_err else None,
        "ball_on_ground_within_1m": round(float(np.mean(np.array(ball_err) < 1.0)), 3) if ball_err else None,
    }
    res["passes"]["in_shot"] = len(vis)
    res["passes"]["recall_in_shot"] = round(hit / len(vis), 3) if vis else None
    res.update({"seed": seed, "window_min": [from_min, from_min + minutes], "view": "broadcast camera", "resolution": f"{width}x{height}",
                "noise_sigma": noise, "frames": len(ae.ball_track)})
    return res


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--from-min", type=float, default=20)
    ap.add_argument("--minutes", type=float, default=5)
    a = ap.parse_args()
    print(json.dumps(evaluate(a.seed, a.from_min, a.minutes), indent=1))
