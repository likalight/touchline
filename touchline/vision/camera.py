"""Broadcast camera: a calibrated pinhole camera on the main stand, panning with play.

Used to render the synthetic match as broadcast-style video (highlights) and, inversely,
to map pixels back onto the pitch for auto-eventing from an angled feed. The same model
is mirrored in web/app.js for the live TV view.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from touchline.schema import PITCH_L, PITCH_W, Event

FONT_DIR = __import__("pathlib").Path(__file__).resolve().parent / "fonts"


@dataclass
class Camera:
    width: int = 1280
    height: int = 720
    cam_y: float = -40.0     # behind the near touchline (y = 0)
    cam_z: float = 23.0      # height of the gantry
    fov_deg: float = 30.0
    tx: float = 52.5         # pan target on the pitch
    ty: float = 30.0

    def basis(self):
        c = np.array([self.tx, self.cam_y, self.cam_z])
        t = np.array([self.tx, self.ty, 0.0])
        f = t - c
        f /= np.linalg.norm(f)
        r = np.cross(f, [0, 0, 1.0])
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        return c, f, r, u

    @property
    def focal(self) -> float:
        return (self.width / 2) / math.tan(math.radians(self.fov_deg / 2))

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """pts: (N,3) world metres -> (N,2) pixels, depth."""
        c, f, r, u = self.basis()
        d = pts - c
        zc = d @ f
        xc, yc = d @ r, d @ u
        fl = self.focal
        zc_safe = np.maximum(zc, 0.1)
        px = np.stack([self.width / 2 + fl * xc / zc_safe, self.height / 2 - fl * yc / zc_safe], axis=1)
        return px, zc

    def to_ground(self, u: float, v: float) -> tuple[float, float]:
        """Pixel -> pitch coordinates by intersecting the viewing ray with the ground plane."""
        c, f, r, up = self.basis()
        fl = self.focal
        d = f + ((u - self.width / 2) / fl) * r - ((v - self.height / 2) / fl) * up
        if d[2] >= -1e-6:
            return float("nan"), float("nan")
        t = -c[2] / d[2]
        p = c + t * d
        return float(p[0]), float(p[1])

    def follow(self, bx: float, by: float, k: float = 0.08) -> None:
        self.tx += (min(max(bx, 24.0), PITCH_L - 24.0) - self.tx) * k
        self.ty += ((30.0 + (by - 34.0) * 0.18) - self.ty) * k


# ------------------------------------------------------------------ scene state from events
def ball_state(ev: Event, t: float) -> Optional[tuple[float, float, float]]:
    """Ball position (x, y, height) at time t during event ev."""
    if ev.x is None:
        return None
    if ev.end_x is None:
        return ev.x, ev.y, 0.11
    q = ev.qualifiers
    spd = (q.get("ball_speed_kmh") or q.get("shot_speed_kmh") or q.get("speed_kmh") or 20) / 3.6
    d = math.hypot(ev.end_x - ev.x, ev.end_y - ev.y)
    dur = max(d / spd, 0.05)
    k = min(1.0, max(0.0, (t - ev.t) / dur))
    h = 0.11
    if ev.type == "pass" and q.get("height") == "high":
        h += 4 * min(14.0, d / 3.2) * k * (1 - k)
    elif ev.type == "shot":
        h += 4 * (1.2 if q.get("body_part") == "foot" else 0.6) * k * (1 - k) + 0.9 * k
    return ev.x + (ev.end_x - ev.x) * k, ev.y + (ev.end_y - ev.y) * k, h


class Scene:
    """Interpolates players and ball between tracked events (shot flight kept until it lands)."""

    def __init__(self, events: list[Event]):
        self.evs = [e for e in events if e.frame is not None]
        self.i = 0

    def at(self, t: float):
        evs = self.evs
        while self.i + 1 < len(evs) and evs[self.i + 1].t <= t:
            self.i += 1
        while self.i > 0 and evs[self.i].t > t:
            self.i -= 1
        a = evs[self.i]
        b = evs[self.i + 1] if self.i + 1 < len(evs) else a
        k = min(1.0, max(0.0, (t - a.t) / max(b.t - a.t, 1e-6)))
        players = {pid: (x0 + (b.frame.get(pid, (x0, y0))[0] - x0) * k, y0 + (b.frame.get(pid, (x0, y0))[1] - y0) * k)
                   for pid, (x0, y0) in a.frame.items()}
        src = a
        for back in (evs[self.i - 1] if self.i else None, a):
            if back is not None and back.type == "shot" and back.end_x is not None:
                q = back.qualifiers
                flight = math.hypot(back.end_x - back.x, back.end_y - back.y) / max(q.get("shot_speed_kmh", 90) / 3.6, 1)
                # keep the ball in flight, then in the net / keeper's hands until play restarts
                if back.t <= t and (t < back.t + flight or a.type in ("goal", "save") or a is back):
                    src = back
        return players, ball_state(src, t), a


# ------------------------------------------------------------------ renderer
def _font(size: int, bold: bool = True):
    name = "BarlowCondensed-Bold.woff2" if bold else "Barlow-Medium.woff2"
    for cand in (FONT_DIR / name.replace(".woff2", ".ttf"), FONT_DIR / name):
        try:
            return ImageFont.truetype(str(cand), size)
        except Exception:
            continue
    return ImageFont.load_default()


class BroadcastRenderer:
    """Renders the synthetic match as a broadcast-style frame (PIL), optionally with graphics."""

    def __init__(self, meta, cam: Optional[Camera] = None, noise: float = 0.0, seed: int = 0):
        self.cam = cam or Camera()
        self.meta = meta
        self.kit = {"h": meta.home.color, "a": meta.away.color}
        self.numbers = {p.id: p.number for p in meta.home.players + meta.away.players}
        self.noise = noise
        self.rng = np.random.default_rng(seed)
        self.f_num = _font(15)
        self.f_bug = _font(30)
        self.f_lt = _font(40)
        self.f_ln = _font(24, bold=False)

    @staticmethod
    def _hex(c: str, k: float = 1.0) -> tuple[int, int, int]:
        c = c.lstrip("#")
        return tuple(max(0, min(255, int(int(c[i:i + 2], 16) * k))) for i in (0, 2, 4))

    def _poly(self, d, pts3, fill=None, outline=None, width=1):
        px, z = self.cam.project(np.array(pts3, float))
        if (z <= 0.5).any():
            return
        d.polygon([tuple(p) for p in px], fill=fill, outline=outline, width=width)

    def _line(self, d, pts3, fill, width=2):
        px, z = self.cam.project(np.array(pts3, float))
        pts = [tuple(p) for p, zz in zip(px, z) if zz > 0.5]
        if len(pts) >= 2:
            d.line(pts, fill=fill, width=width, joint="curve")

    def pitch(self, d: ImageDraw.ImageDraw) -> None:
        W, H = self.cam.width, self.cam.height
        d.rectangle([0, 0, W, H], fill=(16, 44, 33))
        # far stand
        self._poly(d, [(-30, 78, 0), (135, 78, 0), (135, 78, 14), (-30, 78, 14)], fill=(11, 31, 23))
        self._poly(d, [(-30, 78, 14), (135, 78, 14), (135, 92, 26), (-30, 92, 26)], fill=(20, 40, 33))
        # run-off and stripes
        self._poly(d, [(-6, -6, 0), (PITCH_L + 6, -6, 0), (PITCH_L + 6, PITCH_W + 6, 0), (-6, PITCH_W + 6, 0)], fill=(24, 74, 50))
        n = 18
        for k in range(n):
            x0, x1 = k * PITCH_L / n, (k + 1) * PITCH_L / n
            col = (31, 92, 61) if k % 2 else (28, 84, 56)
            self._poly(d, [(x0, 0, 0), (x1, 0, 0), (x1, PITCH_W, 0), (x0, PITCH_W, 0)], fill=col)
        chalk = (208, 216, 202)
        self._line(d, [(0, 0, 0), (PITCH_L, 0, 0), (PITCH_L, PITCH_W, 0), (0, PITCH_W, 0), (0, 0, 0)], chalk, 2)
        self._line(d, [(PITCH_L / 2, 0, 0), (PITCH_L / 2, PITCH_W, 0)], chalk, 2)
        circ = [(PITCH_L / 2 + 9.15 * math.cos(a), PITCH_W / 2 + 9.15 * math.sin(a), 0) for a in np.linspace(0, 2 * math.pi, 48)]
        self._line(d, circ, chalk, 2)
        for side in (0, 1):
            x0 = PITCH_L - 16.5 if side else 16.5
            xe = PITCH_L if side else 0
            self._line(d, [(xe, PITCH_W / 2 - 20.16, 0), (x0, PITCH_W / 2 - 20.16, 0), (x0, PITCH_W / 2 + 20.16, 0), (xe, PITCH_W / 2 + 20.16, 0)], chalk, 2)
            x6 = PITCH_L - 5.5 if side else 5.5
            self._line(d, [(xe, PITCH_W / 2 - 9.16, 0), (x6, PITCH_W / 2 - 9.16, 0), (x6, PITCH_W / 2 + 9.16, 0), (xe, PITCH_W / 2 + 9.16, 0)], chalk, 2)
            # goal frame
            gy0, gy1 = PITCH_W / 2 - 3.66, PITCH_W / 2 + 3.66
            gx = PITCH_L + (0.0 if side else 0) if side else 0.0
            back = gx + (1.8 if side else -1.8)
            self._poly(d, [(gx, gy0, 0), (back, gy0, 0), (back, gy0, 2.2), (gx, gy0, 2.44)], fill=(60, 88, 72))
            self._line(d, [(gx, gy0, 0), (gx, gy0, 2.44), (gx, gy1, 2.44), (gx, gy1, 0)], (250, 250, 250), 3)

    def players(self, d: ImageDraw.ImageDraw, players: dict, focus: Optional[str] = None) -> list:
        items = []
        for pid, (x, y) in players.items():
            px, z = self.cam.project(np.array([[x, y, 0.0], [x, y, 1.82]]))
            if z[0] <= 0.5:
                continue
            items.append((z[0], pid, px))
        boxes = []
        for _, pid, px in sorted(items, key=lambda r: -r[0]):
            (fx_, fy_), (hx, hy) = px
            h = max(fy_ - hy, 6)
            w = h * 0.3
            gk = pid.endswith("1") and len(pid) == 2
            shirt = self._hex(self.kit[pid[0]]) if not gk else ((120, 200, 255) if pid[0] == "h" else (255, 175, 100))
            shorts = self._hex(self.kit[pid[0]], 0.45) if not gk else (40, 40, 40)
            d.ellipse([fx_ - w * 0.9, fy_ - w * 0.25, fx_ + w * 0.9, fy_ + w * 0.25], fill=(14, 40, 27))
            d.rectangle([fx_ - w * 0.32, fy_ - h * 0.42, fx_ + w * 0.32, fy_ - 1], fill=(30, 30, 30))  # legs
            d.rectangle([fx_ - w * 0.5, fy_ - h * 0.55, fx_ + w * 0.5, fy_ - h * 0.38], fill=shorts)
            d.rounded_rectangle([fx_ - w * 0.55, fy_ - h * 0.86, fx_ + w * 0.55, fy_ - h * 0.53], radius=max(1, w * 0.25), fill=shirt)
            d.ellipse([fx_ - w * 0.26, fy_ - h, fx_ + w * 0.26, fy_ - h * 0.84], fill=(196, 150, 118))
            if h > 46:
                d.text((fx_, fy_ - h * 0.7), str(self.numbers.get(pid, "")), fill=(255, 255, 255), font=self.f_num, anchor="mm")
            if pid == focus:
                d.ellipse([fx_ - w * 1.3, fy_ - w * 0.4, fx_ + w * 1.3, fy_ + w * 0.4], outline=(242, 193, 78), width=3)
            boxes.append((pid, fx_, fy_, h))
        return boxes

    def ball(self, d: ImageDraw.ImageDraw, ball) -> None:
        if not ball:
            return
        x, y, z = ball
        px, depth = self.cam.project(np.array([[x, y, 0.0], [x, y, z]]))
        if depth[1] <= 0.5:
            return
        r = max(2.5, self.cam.focal * 0.24 / depth[1])
        sx, sy = px[0]
        d.ellipse([sx - r * 1.2, sy - r * 0.45, sx + r * 1.2, sy + r * 0.45], fill=(14, 40, 27))
        bx, by = px[1]
        d.ellipse([bx - r, by - r, bx + r, by + r], fill=(255, 255, 255))

    def scorebug(self, d: ImageDraw.ImageDraw, score: dict, minute: int) -> None:
        m = self.meta
        x, y = 36, 28
        segs = [(m.home.short, (24, 66, 50), (238, 240, 232)), (f"{score['home']}-{score['away']}", (238, 240, 232), (15, 43, 32)),
                (m.away.short, (24, 66, 50), (238, 240, 232)), (f"{minute}'", (242, 193, 78), (43, 33, 0))]
        for text, bg, fg in segs:
            w = d.textlength(text, font=self.f_bug) + 26
            d.rectangle([x, y, x + w, y + 44], fill=bg)
            d.text((x + w / 2, y + 22), text, fill=fg, font=self.f_bug, anchor="mm")
            x += w

    def lower_third(self, d: ImageDraw.ImageDraw, title: str, line: str = "", alpha: float = 1.0) -> None:
        W, H = self.cam.width, self.cam.height
        tw = max(d.textlength(title, font=self.f_lt), d.textlength(line, font=self.f_ln)) + 48
        x0, y0 = 48, H - 150
        wclip = tw * min(1.0, alpha)
        d.rectangle([x0, y0, x0 + 10, y0 + 104], fill=(242, 193, 78))
        d.rectangle([x0 + 10, y0, x0 + 10 + wclip, y0 + 104], fill=(12, 36, 27))
        if alpha >= 0.6:
            d.text((x0 + 32, y0 + 14), title, fill=(238, 240, 232), font=self.f_lt)
            if line:
                d.text((x0 + 32, y0 + 64), line, fill=(222, 228, 214), font=self.f_ln)

    def frame(self, players, ball, focus=None, score=None, minute=None, lt=None) -> Image.Image:
        img = Image.new("RGB", (self.cam.width, self.cam.height))
        d = ImageDraw.Draw(img)
        self.pitch(d)
        self.players(d, players, focus)
        self.ball(d, ball)
        if score is not None:
            self.scorebug(d, score, minute)
        if lt:
            self.lower_third(d, *lt)
        if self.noise:
            arr = np.asarray(img).astype(np.int16)
            arr = np.clip(arr + self.rng.normal(0, self.noise, arr.shape).astype(np.int16), 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)
        return img
