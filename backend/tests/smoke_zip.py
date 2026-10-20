"""ZIP upload: one drop becomes a full course (video + captions + PDF)."""
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
ZIP = os.path.join(os.environ.get("TEMP", "."), "l2h_zip", "lecture.zip")
ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


c = httpx.Client(base_url=BASE, timeout=300.0)
H = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"}).json()["access_token"]}
course = c.post("/api/courses", headers=H, json={"title": "ZIP course", "description": "from zip"}).json()
cid = course["id"]

with open(ZIP, "rb") as f:
    r = c.post(f"/api/courses/{cid}/materials", headers=H, files={"file": ("lecture.zip", f, "application/zip")})
check("zip upload 200", r.status_code == 200, f"status={r.status_code} {str(r.json())[:150]}")

mats = {m["filename"]: m for m in r.json()["materials"]}
check("all 3 files registered", all(k in mats for k in ("lecture1.mp4", "lecture1.vtt", "notes.pdf")), str(list(mats)))
check("kinds classified", mats["lecture1.mp4"]["kind"] == "video" and mats["notes.pdf"]["kind"] == "pdf", str({k: v["kind"] for k, v in mats.items()}))

c.post(f"/api/courses/{cid}/ingest", headers=H)
st = ""
for _ in range(60):
    time.sleep(2)
    s = c.get(f"/api/courses/{cid}/status", headers=H).json()
    st = s["status"]
    if st in ("ready", "error"):
        break
check("zip course builds -> ready", st == "ready", f"status={st} chunks={s.get('chunks')} err={s.get('error','')[:100]}")

if st == "ready":
    a = c.post("/api/ask", headers=H, json={"course_id": cid, "question": "What is a queue?", "video_time": 100}).json()
    check("zip course answers", a.get("in_material"), str(a.get("answer"))[:90])

# a bad zip must be rejected honestly
bad = os.path.join(os.environ.get("TEMP", "."), "l2h_zip", "bad.zip")
with open(bad, "wb") as f:
    f.write(b"this is not a zip at all")
c2 = c.post("/api/courses", headers=H, json={"title": "Bad zip", "description": "x"}).json()
with open(bad, "rb") as f:
    r2 = c.post(f"/api/courses/{c2['id']}/materials", headers=H, files={"file": ("bad.zip", f, "application/zip")})
check("broken zip rejected", r2.status_code == 400, f"status={r2.status_code}")

for x in (cid, c2["id"]):
    c.delete(f"/api/courses/{x}", headers=H)
print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
sys.exit(0 if ok else 1)
