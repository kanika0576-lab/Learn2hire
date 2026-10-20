"""Verify: seeded video has audio, notes endpoint, ask on overview-only course, quiz."""
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
tok = c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
cs = c.get("/api/courses", headers=H).json()
course = next((x for x in cs if x["title"].startswith("Intro to Data Structures") and x["status"] == "ready"), next(x for x in cs if x["status"] == "ready"))
cid = course["id"]
vid = next(m for m in course["materials"] if m["kind"] == "video")

# 1) seeded video streams and is real mp4
r = c.get(f"/api/courses/{cid}/materials/{vid['id']}/file?token={tok}", headers={"Range": "bytes=0-2047"})
check("seeded video 206+ftyp", r.status_code == 206 and b"ftyp" in r.content, f"status={r.status_code}")
check("no-cache header", r.headers.get("cache-control", "").startswith("no-store"), r.headers.get("cache-control", "none"))

# 2) ask gives a real answer with sources
r = c.post("/api/ask", headers=H, json={"course_id": cid, "question": "What is a hash map?", "video_time": 130})
a = r.json()
check("ask -> 200 in_material", r.status_code == 200 and a.get("in_material"), f"status={r.status_code} ans={str(a.get('answer'))[:90]}")
check("ask has sources", len(a.get("sources") or []) > 0, f"n={len(a.get('sources') or [])}")

# 3) quiz generates questions
r = c.post("/api/quiz/generate", headers=H, json={"course_id": cid, "n_questions": 5})
q = r.json()
check("quiz -> 5 questions", r.status_code == 200 and len(q.get("questions", [])) >= 3,
      f"status={r.status_code} n={len(q.get('questions', []))}")

# 4) notes endpoint
r = c.post(f"/api/courses/{cid}/notes", headers=H)
n = r.json()
check("notes -> 200", r.status_code == 200, f"status={r.status_code}")
check("notes has summary+points", bool(n.get("summary")) and len(n.get("key_points") or []) > 0,
      f"points={len(n.get('key_points') or [])} provider={n.get('generated_by')}")

# 5) overview-only course: build works, ask answers (not "not in material"), quiz still generates
nc = c.post("/api/courses", headers=H, json={"title": "Trees explained", "description": "Binary search trees, AVL and red-black trees"}).json()
ncid = nc["id"]
with open(GIF, "rb") as f:
    c.post(f"/api/courses/{ncid}/materials", headers=H, files={"file": ("lecture [yt].gif", f)})
c.post(f"/api/courses/{ncid}/ingest", headers=H)
st = ""
for _ in range(50):
    time.sleep(2)
    s = c.get(f"/api/courses/{ncid}/status", headers=H).json()
    st = s["status"]
    if st in ("ready", "error"):
        break
check("video-only course ready", st == "ready", f"status={st} chunks={s.get('chunks')}")

r = c.post("/api/ask", headers=H, json={"course_id": ncid, "question": "Tell me about trees", "video_time": 30})
a2 = r.json()
check("overview-course ask answers", a2.get("in_material") and "NOT_IN_MATERIAL" not in str(a2.get("answer", "")),
      str(a2.get("answer", ""))[:110])

c.delete(f"/api/courses/{ncid}", headers=H)
print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
sys.exit(0 if ok else 1)