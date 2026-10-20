"""End-to-end: video ?token= auth fix + full build-knowledge-base flow."""
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
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

cs = c.get("/api/courses", headers=H).json()
course = cs[0]
cid = course["id"]
vid = next(m for m in course["materials"] if m["kind"] == "video")

# 1) video without auth -> 401
r = c.get(f"/api/courses/{cid}/materials/{vid['id']}/file", headers={"Range": "bytes=0-31"})
check("video no-auth -> 401", r.status_code == 401, f"status={r.status_code}")

# 2) video with ?token= -> 206 + ftyp
r = c.get(f"/api/courses/{cid}/materials/{vid['id']}/file?token={tok}", headers={"Range": "bytes=0-31"})
check("video ?token= -> 206+ftyp",
      r.status_code == 206 and b"ftyp" in r.content,
      f"status={r.status_code} len={len(r.content)}")

# 3) FULL BUILD FLOW: create course, upload avif+vtt, ingest -> ready
nc = c.post("/api/courses", headers=H, json={"title": "Build KB test", "description": "build"}).json()
ncid = nc["id"]
avif = GIF
with open(avif, "rb") as f:
    c.post(f"/api/courses/{ncid}/materials", headers=H, files={"file": ("lecture [yt].gif", f)})
vtt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "sample", "lecture1.vtt")
with open(vtt, "rb") as f:
    c.post(f"/api/courses/{ncid}/materials", headers=H, files={"file": ("captions.vtt", f)})
r = c.post(f"/api/courses/{ncid}/ingest", headers=H)
check("ingest start 200", r.status_code == 200, r.text[:100])

status = ""
for _ in range(50):
    time.sleep(2)
    s = c.get(f"/api/courses/{ncid}/status", headers=H).json()
    status = s["status"]
    if status in ("ready", "error"):
        break
check("build KB -> ready", status == "ready",
      f"status={status} error={s.get('error','')[:90]} chunks={s.get('chunks')}")

# 4) video of the new course plays
new_vid = next(m for m in s["materials"] if m["kind"] == "video")
r = c.get(f"/api/courses/{ncid}/materials/{new_vid['id']}/file?token={tok}", headers={"Range": "bytes=0-31"})
check("new-course video plays (206+ftyp)", r.status_code == 206 and b"ftyp" in r.content,
      f"status={r.status_code}")

# cleanup
c.delete(f"/api/courses/{ncid}", headers=H)
print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
sys.exit(0 if ok else 1)
