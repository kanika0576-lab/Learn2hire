"""End-to-end: upload a YouTube-style .mkv + .vtt (like yt-dlp output), ingest,
verify the video is remuxed to browser-playable mp4 and the tutor answers."""

import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
MKV = os.path.join(os.environ.get("TEMP", "."), "lecture1_yt.mkv")
VTT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "sample", "lecture1.vtt")
ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


c = httpx.Client(base_url=BASE, timeout=300.0)
email = f"yt{int(time.time())}@test.dev"
r = c.post("/api/auth/register", json={"name": "YT Tester", "email": email, "password": "testpass1"})
check("register", r.status_code == 200, r.text[:100])
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

r = c.post("/api/courses", headers=H, json={"title": "YouTube MKV test", "description": "mkv remux"})
course = r.json()
check("course created", r.status_code == 200, str(course.get("id", ""))[:40])

with open(MKV, "rb") as f:
    r = c.post(f"/api/courses/{course['id']}/materials", headers=H, files={"file": ("Lecture_01 [yt-dlp].mkv", f, "video/x-matroska")})
check("mkv upload accepted", r.status_code == 200, r.text[:150])

with open(VTT, "rb") as f:
    r = c.post(f"/api/courses/{course['id']}/materials", headers=H, files={"file": ("Lecture_01 [yt-dlp].en.vtt", f, "text/vtt")})
check("vtt upload accepted", r.status_code == 200, r.text[:150])

r = c.post(f"/api/courses/{course['id']}/ingest", headers=H)
check("ingest started", r.status_code == 200, r.text[:100])

deadline = time.time() + 180
status = ""
while time.time() < deadline:
    time.sleep(2)
    status = c.get(f"/api/courses/{course['id']}/status", headers=H).json()["status"]
    if status in ("ready", "error"):
        break
info = c.get(f"/api/courses/{course['id']}/status", headers=H).json()
check("ingest -> ready", status == "ready", str(info)[:300])

vid = next((m for m in info["materials"] if m["kind"] == "video"), None)
check("video remuxed to mp4", vid is not None and vid["filename"].endswith(".mp4"), str(vid))

if vid:
    r = c.get(f"/api/courses/{course['id']}/materials/{vid['id']}/file", headers={**H, "Range": "bytes=0-31"})
    body = r.content
    check("mp4 streams (206, ftyp)", r.status_code == 206 and b"ftyp" in body, f"status={r.status_code} head={body[:16]!r}")

r = c.post("/api/ask", headers=H, json={"course_id": course["id"], "question": "What is a stack?", "video_time": 60})
j = r.json()
check("tutor answers from mkv course", r.status_code == 200 and j["in_material"], j.get("answer", "")[:120])

print("\nYT-MKV FLOW PASSED" if ok else "\nFAILURES")
sys.exit(0 if ok else 1)
