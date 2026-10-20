"""Animated-image uploads: an animated GIF becomes a real playable mp4,
while a still image (.avif thumbnail) is reported honestly instead of
silently becoming a 1-second 'lecture'."""

import os
import subprocess
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
TEMP = os.environ.get("TEMP", ".")
SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "sample")
ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


def make_gif(path: str, seconds: int = 20) -> bool:
    src = os.path.join(SAMPLE, "lecture1.mp4")
    if not os.path.exists(src):
        return False
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-t", str(seconds),
         "-vf", "fps=5,scale=480:-2", path],
        capture_output=True,
    )
    return r.returncode == 0 and os.path.exists(path)


c = httpx.Client(base_url=BASE, timeout=300.0)
tok = c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
VTT = os.path.join(SAMPLE, "lecture1.vtt")


def build_with(path: str, name: str, title: str) -> tuple[str, dict]:
    cid = c.post("/api/courses", headers=H, json={"title": title, "description": "animated image"}).json()["id"]
    with open(path, "rb") as f:
        c.post(f"/api/courses/{cid}/materials", headers=H, files={"file": (name, f)})
    with open(VTT, "rb") as f:
        c.post(f"/api/courses/{cid}/materials", headers=H, files={"file": ("captions.vtt", f)})
    c.post(f"/api/courses/{cid}/ingest", headers=H)
    st = ""
    info: dict = {}
    for _ in range(60):
        time.sleep(2)
        info = c.get(f"/api/courses/{cid}/status", headers=H).json()
        st = info["status"]
        if st in ("ready", "error"):
            break
    return cid, info


# 1) animated GIF -> real, playable mp4
gif = os.path.join(TEMP, "l2h_anim.gif")
if make_gif(gif):
    cid, info = build_with(gif, "lecture [yt].gif", "Animated GIF lecture")
    check("animated gif -> ready", info["status"] == "ready", f"status={info['status']} err={info.get('error','')[:90]}")
    vid = next((m for m in info["materials"] if m["kind"] == "video"), None)
    check("gif converted to .mp4", bool(vid) and vid["filename"].endswith(".mp4"), str(vid))
    if vid:
        r = c.get(f"/api/courses/{cid}/materials/{vid['id']}/file?token={tok}", headers={"Range": "bytes=0-31"})
        check("converted mp4 streams (206+ftyp)", r.status_code == 206 and b"ftyp" in r.content, f"status={r.status_code}")
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              f"{TEMP}\\l2h_narr\\anim_gif.mp4"], capture_output=True, text=True).stdout.strip()
        check("converted video keeps full length", float(dur) > 15, f"duration={dur}s")
    c.delete(f"/api/courses/{cid}", headers=H)
else:
    print("[SKIP] could not build animated gif fixture")

# 2) still .avif -> honest error, never a fake 1s "ready" lecture
still = os.path.join(TEMP, "still.avif")
if os.path.exists(still):
    cid, info = build_with(still, "lecture.avif", "Still image avif")
    check("still avif -> error", info["status"] == "error", f"status={info['status']}")
    check("error explains it's a still image", "still image" in info.get("error", "").lower(),
          info.get("error", "")[:120])
    c.delete(f"/api/courses/{cid}", headers=H)
else:
    print("[SKIP] still.avif not present")

print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
sys.exit(0 if ok else 1)