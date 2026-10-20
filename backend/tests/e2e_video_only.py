"""Video-only KB build (no transcript) + video play via frontend proxy."""
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
TEMP = os.environ.get("TEMP", ".")

def _gif_fixture() -> str:
    """Build an animated GIF from the sample lecture (animated-image upload path)."""
    import subprocess

    out = os.path.join(TEMP, "l2h_anim.gif")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "sample", "lecture1.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-t", "20",
                    "-vf", "fps=5,scale=480:-2", out], capture_output=True)
    return out


GIF = _gif_fixture()
ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


c = httpx.Client(base_url=BASE, timeout=300.0)
r = c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"})
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# Create course, upload ONLY avif (no transcript), build KB
nc = c.post("/api/courses", headers=H, json={"title": "Video-only course", "description": "Arrays and linked lists explained"}).json()
ncid = nc["id"]
avif = GIF
with open(avif, "rb") as f:
    c.post(f"/api/courses/{ncid}/materials", headers=H, files={"file": ("lecture [yt].gif", f)})
c.post(f"/api/courses/{ncid}/ingest", headers=H)
status = ""
for _ in range(50):
    time.sleep(2)
    s = c.get(f"/api/courses/{ncid}/status", headers=H).json()
    status = s["status"]
    if status in ("ready", "error"):
        break
check("video-only build KB -> ready", status == "ready",
      f"status={status} error={s.get('error','')[:90]} chunks={s.get('chunks')}")
# Open page should be 200 (player + banner, not dead-end)
pg = httpx.get(f"http://127.0.0.1:3000/course/{ncid}", timeout=25)
check("course page (video-only) -> 200", pg.status_code == 200, f"status={pg.status_code}")

# Video plays via frontend proxy with ?token=
new_vid = next(m for m in s["materials"] if m["kind"] == "video")
r = c.get(f"/api/courses/{ncid}/materials/{new_vid['id']}/file?token={tok}", headers={"Range": "bytes=0-31"})
check("video plays 206+ftyp", r.status_code == 206 and b"ftyp" in r.content,
      f"status={r.status_code} ct={r.headers.get('content-type')}")

# Also via frontend proxy (rewrite passes query string)
pr = httpx.get(f"{FE}/api/courses/{ncid}/materials/{new_vid['id']}/file?token={tok}",
               headers={"Range": "bytes=0-31"}, timeout=20)
check("video via proxy 206+ftyp", pr.status_code == 206 and b"ftyp" in pr.content,
      f"status={pr.status_code}")

# cleanup
c.delete(f"/api/courses/{ncid}", headers=H)
print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
sys.exit(0 if ok else 1)
