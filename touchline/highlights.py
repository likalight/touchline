"""My Match: a personal recap and an auto-cut highlights reel for every fan.

`plan_reel` picks clips from the verified insights, scored by salience *and* by what this
fan cares about (their club, the player they follow), and writes a timed edit decision
list (EDL). `render_reel` renders that EDL through the broadcast camera with a
scorebug, lower-thirds in the fan's language, title and end cards, and encodes an MP4.
With Azure AI Speech configured, each clip's line is voiced and mixed in.

The same EDL is a highlights package for a studio: clip in/out on the match clock,
title, the event IDs it shows and the verified copy, ready for an editor.
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

from touchline.vision.camera import BroadcastRenderer, Scene

PRE_POST = {
    "goal": (8.0, 3.5), "chance_saved": (6.0, 2.5), "chance_missed": (6.0, 2.0), "chance_blocked": (5.0, 1.5),
    "card_red": (5.0, 3.0), "line_break": (3.5, 2.5), "hard_pass": (3.0, 2.0), "sprint": (3.0, 2.0), "long_carry": (3.0, 2.0),
    "story_duel": (3.0, 2.5), "record_shot": (4.0, 2.0), "hat_trick": (0, 0), "brace": (0, 0),
}
CARD_WORDS = {
    "en": {"mine": "My Match", "foot": "Synthetic match, fictional clubs. Every line checked against the match data."},
    "es": {"mine": "Mi partido", "foot": "Partido sintético, clubes ficticios. Cada línea, verificada con los datos del partido."},
    "fr": {"mine": "Mon match", "foot": "Match synthétique, clubs fictifs. Chaque ligne vérifiée avec les données du match."},
    "pt": {"mine": "O meu jogo", "foot": "Jogo sintético, clubes fictícios. Cada linha verificada com os dados do jogo."},
}
POSITIVE = {"goal", "chance_saved", "chance_missed", "line_break", "hard_pass", "sprint", "long_carry", "story_duel", "record_shot"}


def plan_reel(session, club: Optional[str] = None, player: Optional[str] = None, lang: str = "en",
              persona: str = "casual", budget_s: float = 75.0) -> dict:
    s = session.state
    scored = []
    for ins in session.insights:
        k = ins["kind"]
        if k not in PRE_POST or PRE_POST[k] == (0, 0) or ins.get("verification", {}).get("status") != "verified":
            continue
        rel = ins["salience"]
        if club and ins["team"] == club and k in POSITIVE:
            rel += 0.35
        if club and ins["team"] and ins["team"] != club and k == "goal":
            rel += 0.15  # a fan still wants to see the goals against
        involved = {ins.get("player_id")} | {s.events[e].player_id for e in ins["event_ids"] if e in s.events} \
            | {s.events[e].target_id for e in ins["event_ids"] if e in s.events}
        if player and player in involved:
            rel += 0.5
        if k == "goal":
            rel += 1.0  # every goal makes the reel
        scored.append((rel, ins))
    scored.sort(key=lambda r: -r[0])
    clips, used = [], 0.0
    for rel, ins in scored:
        pre, post = PRE_POST[ins["kind"]]
        anchor = ins["t"]
        if ins["kind"] == "goal":  # anchor on the shot itself (callbacks may cite earlier events)
            shots = [s.events[e] for e in ins["event_ids"] if e in s.events and s.events[e].type == "shot" and s.events[e].t <= ins["t"]]
            anchor = shots[-1].t if shots else ins["t"]
        start, end = max(0.0, anchor - pre), anchor + post
        if any(not (end < c["start"] - 2 or start > c["end"] + 2) for c in clips):
            continue
        if used + (end - start) > budget_s and ins["kind"] != "goal":
            continue
        by = ins["renders"].get(persona, {})
        r = by.get(lang) or by.get("en")
        if not r:
            continue
        story = [l for l in r["lines"] if l.get("k", "").startswith("s.")]
        line = (story[-1] if story else (r["lines"][0] if r["lines"] else {"text": ""}))["text"]
        clips.append({"start": round(start, 2), "end": round(end, 2), "insight_id": ins["id"], "kind": ins["kind"],
                      "minute": ins["minute"], "team": ins["team"], "title": r["title"],
                      "line": line, "evidence": ins["event_ids"],
                      "relevance": round(rel, 2), "focus": player if player in (ins.get("player_id"),) else None})
        used += end - start
    clips.sort(key=lambda c: c["start"])
    recap = session.get_recap(persona, lang)
    return {"schema": "touchline.reel/1", "match_id": session.meta.match_id, "club": club, "player": player, "lang": lang,
            "persona": persona, "duration_s": round(used, 1), "clips": clips,
            "recap": {"title": recap["title"], "lines": [l["text"] for l in recap["lines"]]}}


def _score_at(events, t: float) -> dict:
    sc = {"home": 0, "away": 0}
    for e in events:
        if e.t > t:
            break
        if e.type == "goal":
            sc[e.team] += 1
    return sc


def render_reel(session, edl: dict, out_path: str, fps: int = 25, width: int = 1280, height: int = 720,
                voice: Optional[list[bytes]] = None) -> str:
    """Render the EDL through the broadcast camera and encode H.264 (needs ffmpeg)."""
    from PIL import Image, ImageDraw

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    meta, events = session.meta, session.events
    rend = BroadcastRenderer(meta)
    rend.cam.width, rend.cam.height = width, height
    scene = Scene(events)
    proc = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                             "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
    club = edl.get("club")
    accent = rend._hex((meta.home if club != "away" else meta.away).color)

    def card(lines: list[tuple[str, int, bool]], seconds: float, bg=(15, 43, 32)):
        img = Image.new("RGB", (width, height), bg)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 18, height], fill=accent)
        y = height * 0.33
        for text, size, bold in lines:
            f = rend.f_lt if bold and size >= 40 else (rend.f_bug if bold else rend.f_ln)
            if size >= 60:
                from touchline.vision.camera import _font
                f = _font(size)
            d.text((80, y), text, fill=(238, 240, 232), font=f)
            y += size * 1.25
        buf = np.asarray(img).tobytes()
        for _ in range(int(seconds * fps)):
            proc.stdin.write(buf)

    h, a = meta.home, meta.away
    final = session.state.score
    who = {"home": h.name, "away": a.name}.get(club or "", "")
    words = CARD_WORDS.get(edl.get("lang", "en"), CARD_WORDS["en"])
    card([(words["mine"] + (f": {who}" if who else ""), 30, True), (f"{h.short} {final['home']}-{final['away']} {a.short}", 96, True),
          (edl["recap"]["lines"][0] if edl["recap"]["lines"] else "", 24, False)], 2.4)
    for c in edl["clips"]:
        # settle the camera on the action before the clip starts
        for k in range(30):
            pl, b, _ = scene.at(c["start"] - 1.5 + k * 0.05)
            if b:
                rend.cam.follow(b[0], b[1], 0.25)
        n = int((c["end"] - c["start"]) * fps)
        anchor_frac = 0.55 if c["kind"] == "goal" else 0.35
        for i in range(n):
            t = c["start"] + i / fps
            pl, b, _ = scene.at(t)
            if b:
                rend.cam.follow(b[0], b[1], 0.07)
            minute = int(t // 60) + 1
            appear = (i / n - anchor_frac) / 0.08
            lt = (c["title"], c["line"], min(1.0, appear)) if appear > 0 else None
            img = rend.frame(pl, b, focus=edl.get("player"), score=_score_at(events, t), minute=minute, lt=lt)
            proc.stdin.write(img.tobytes())
    card([(edl["recap"]["title"], 44, True)] + [(ln, 24, False) for ln in edl["recap"]["lines"][1:4]] +
         [(words["foot"], 22, False)], 3.2)
    proc.stdin.close()
    proc.wait()
    if voice:
        _mux_voice(out_path, edl, voice, fps)
    return out_path


def _mux_voice(video: str, edl: dict, clips_audio: list[bytes], fps: int) -> None:
    """Place each voiced line at its clip's start (after the 2.4 s title card) and mix into the MP4."""
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    inputs, filters, offset = [], [], 2.4
    for i, (c, wav) in enumerate(zip(edl["clips"], clips_audio)):
        if not wav:
            offset += c["end"] - c["start"]
            continue
        p = tmp / f"v{i}.mp3"
        p.write_bytes(wav)
        inputs += ["-i", str(p)]
        delay = int((offset + (c["end"] - c["start"]) * 0.3) * 1000)
        filters.append(f"[{len(inputs) // 2}:a]adelay={delay}|{delay}[a{i}]")
        offset += c["end"] - c["start"]
    if not filters:
        return
    labels = "".join(f"[a{i}]" for i in range(len(edl["clips"])) if f"[a{i}]" in "".join(filters))
    fc = ";".join(filters) + f";{labels}amix=inputs={len(filters)}:normalize=0[aout]"
    out = str(Path(video).with_suffix(".voiced.mp4"))
    subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error", "-i", video, *inputs, "-filter_complex", fc,
                    "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-shortest", out], check=True)
    Path(out).replace(video)
    _ = math, fps
