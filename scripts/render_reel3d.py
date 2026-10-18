"""Render a My Match reel from the 3D broadcast view to MP4, frame by frame.

Plays a full match on a running Touchline server, opens /reel in headless Chromium with
frame-exact stepping, and pipes each composited frame to ffmpeg.

    python scripts/render_reel3d.py --seed 221 --club home --lang en --out docs/my-match-3d.mp4
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import time
import urllib.request
from urllib.parse import urlencode


def api(base: str, path: str, body: dict | None = None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--seed", type=int, default=221)
    ap.add_argument("--club", default="")
    ap.add_argument("--player", default="")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--out", default="docs/my-match-3d.mp4")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--chrome", default="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    a = ap.parse_args()

    sid = api(a.base, "/api/matches", {"seed": a.seed, "speed": 240})["session_id"]
    api(a.base, f"/api/matches/{sid}/control", {"action": "jump", "value": 200})
    while not api(a.base, f"/api/matches/{sid}").get("done"):
        time.sleep(1)

    from playwright.async_api import async_playwright
    q = urlencode({k: v for k, v in {"session": sid, "club": a.club, "player": a.player, "lang": a.lang, "frames": 1}.items() if v})
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(a.fps), "-i", "-",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", "-movflags", "+faststart", a.out],
                          stdin=subprocess.PIPE)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=a.chrome, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width": 1312, "height": 900})
        pg.on("pageerror", lambda e: print("page error:", e))
        await pg.goto(f"{a.base}/reel?{q}")
        await pg.wait_for_function("window.reelReady && window.reelReady()", timeout=120000)
        n, t0 = 0, time.time()
        while True:
            st = await pg.evaluate(f"window.reelStep({a.fps})")
            data = await pg.evaluate("document.getElementById('comp').toDataURL('image/jpeg', 0.93)")
            ff.stdin.write(base64.b64decode(data.split(",", 1)[1]))
            n += 1
            if n % 250 == 0:
                print(f"{n} frames ({n / a.fps:.0f} s of film), clip {st['clip'] + 1}/{st['clips']}, {time.time() - t0:.0f} s elapsed", flush=True)
            if not st["more"] or (a.max_frames and n >= a.max_frames):
                break
        await b.close()
    ff.stdin.close()
    ff.wait()
    print(f"wrote {a.out}: {n} frames, {n / a.fps:.1f} s")


if __name__ == "__main__":
    asyncio.run(main())
