import sys

import httpx

BASE = "http://127.0.0.1:8000"
ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


c = httpx.Client(base_url=BASE, timeout=300.0)
r = c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"})
check("demo login", r.status_code == 200, r.text[:120])
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

courses = c.get("/api/courses", headers=H).json()
check("seeded course present", len(courses) >= 1, str([x["title"] for x in courses]))
course = next((x for x in courses if x["title"].startswith("Intro to Data Structures") and x["status"] == "ready"), next(x for x in courses if x["status"] == "ready"))
check("course ready", course["status"] == "ready")

video = next(m for m in course["materials"] if m["kind"] == "video")

# full GET
r = c.get(f"/api/courses/{course['id']}/materials/{video['id']}/file", headers=H)
check("full video GET 200", r.status_code == 200, f"status={r.status_code} bytes={len(r.content)}")
check("content-type video/mp4", r.headers.get("content-type", "").startswith("video/mp4"), r.headers.get("content-type", ""))
check("accept-ranges", r.headers.get("accept-ranges") == "bytes", str(r.headers.get("accept-ranges")))
check("starts with mp4 header", r.content[4:8] == b"ftyp", str(r.content[:12]))

# range GET (what the browser sends when seeking)
r = c.get(f"/api/courses/{course['id']}/materials/{video['id']}/file", headers={**H, "Range": "bytes=0-1023"})
check("range GET 206", r.status_code == 206, f"status={r.status_code} bytes={len(r.content)}")
check("content-range", r.headers.get("content-range", "").startswith("bytes 0-1023/"), r.headers.get("content-range", ""))
check("range body 1024B", len(r.content) == 1024, str(len(r.content)))

# pdf works too
pdf = next(m for m in course["materials"] if m["kind"] == "pdf")
r = c.get(f"/api/courses/{course['id']}/materials/{pdf['id']}/file", headers=H)
check("pdf GET 200", r.status_code == 200 and r.content[:5] == b"%PDF-", f"status={r.status_code}")

# auth required
r = httpx.get(BASE + f"/api/courses/{course['id']}/materials/{video['id']}/file", timeout=30)
check("file requires auth", r.status_code in (401, 403), str(r.status_code))

# seeded ask sanity at two timestamps (real course content)
r = c.post("/api/ask", headers=H, json={"course_id": course["id"], "question": "What is a hash map?", "video_time": 130})
j = r.json()
check("seeded ask answers", r.status_code == 200 and j["in_material"], j.get("answer", "")[:150])
r = c.post("/api/ask", headers=H, json={"course_id": course["id"], "question": "Explain red-black trees", "video_time": 60})
j = r.json()
future_video = [s for s in j.get("sources", []) if s["type"] == "video" and (s.get("start_time") or 0) > 60]
check(
    "seeded ask no-spoiler (no video chunk after t=60s)",
    r.status_code == 200 and not future_video,
    str({"covered_later": j.get("covered_later"), "sources": j.get("sources")})[:220],
)

sys.exit(0 if ok else 1)
