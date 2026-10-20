import sys
import httpx

BASE = "http://127.0.0.1:3000"  # through the Next.js rewrite proxy
ok = True

def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False

c = httpx.Client(base_url=BASE, timeout=300.0)
r = c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"})
check("login via proxy", r.status_code == 200, r.text[:80])
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

courses = c.get("/api/courses", headers=H).json()
check("dashboard courses", len(courses) >= 1)
course = next(x for x in courses if x['title'].startswith('Intro to Data Structures'))
check("course ready with materials", course["status"] == "ready" and len(course["materials"]) >= 3)

vid = next(m for m in course["materials"] if m["kind"] == "video")
r = c.get(f"/api/courses/{course['id']}/materials/{vid['id']}/file", headers={**H, "Range": "bytes=0-99"})
check("video seek via proxy (206)", r.status_code == 206, str(r.status_code))

r = c.post("/api/ask", headers=H, json={"course_id": course["id"], "question": "What is a queue?", "video_time": 210})
j = r.json()
check("ask via proxy", r.status_code == 200 and j["in_material"], j.get("answer", "")[:120])

r = c.post("/api/quiz/generate", headers=H, json={"course_id": course["id"], "n_questions": 2})
check("quiz generate via proxy", r.status_code == 200 and len(r.json()["questions"]) == 2, str(r.status_code))

r = c.post("/api/interview/start", headers=H, json={"course_id": course["id"]})
ij = r.json()
check("interview start via proxy", r.status_code == 200 and ij.get("status") == "active", str(ij)[:150])

print("\nALL PROXY E2E PASSED" if ok else "\nFAILURES PRESENT")
sys.exit(0 if ok else 1)
