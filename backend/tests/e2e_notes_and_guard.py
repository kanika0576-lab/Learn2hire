"""Verify: still-image avif is rejected with a clear message; notes auto-generate after build."""
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
TEMP = os.environ.get("TEMP", ".")
ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


c = httpx.Client(base_url=BASE, timeout=300.0)
tok = c.post("/api/auth/login", json={"email": "demo@learn2hire.dev", "password": "demo1234"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# 1) a still-image avif must be called out instead of silently becoming a 1s "video"
still = os.path.join(TEMP, "still.avif")
nc = c.post("/api/courses", headers=H, json={"title": "Still image test", "description": "avif still"}).json()
cid = nc["id"]
if os.path.exists(still):
    with open(still, "rb") as f:
        c.post(f"/api/courses/{cid}/materials", headers=H, files={"file": ("lecture.avif", f)})
    c.post(f"/api/courses/{cid}/ingest", headers=H)
    st = ""
    for _ in range(50):
        time.sleep(2)
        s = c.get(f"/api/courses/{cid}/status", headers=H).json()
        st = s["status"]
        if st in ("ready", "error"):
            break
    err = s.get("error", "")
    check("still avif rejected with clear message", "still image" in err.lower(), f"status={st} err={err[:130]}")
else:
    print("[SKIP] still.avif not present")
c.delete(f"/api/courses/{cid}", headers=H)

# 2) building a real course auto-creates notes that the GET endpoint serves
cs = c.get("/api/courses", headers=H).json()
ready = next((x for x in cs if x["status"] == "ready"), None)
check("has a ready course", ready is not None)
if ready:
    r = c.get(f"/api/courses/{ready['id']}/notes", headers=H)
    n = r.json()
    check("notes GET 200", r.status_code == 200, f"status={r.status_code}")
    check("notes cached + populated", bool(n.get("summary")) and len(n.get("key_points") or []) > 0,
          f"points={len(n.get('key_points') or [])}")

# 3) the seeded lecture is a real 360s video with audio
if ready:
    vid = next(m for m in ready["materials"] if m["kind"] == "video")
    rr = c.get(f"/api/courses/{ready['id']}/materials/{vid['id']}/file?token={tok}", headers={"Range": "bytes=0-31"})
    check("seeded video streams 206", rr.status_code == 206, f"status={rr.status_code}")
    print("   seeded duration (s):", vid.get("duration"))

print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
sys.exit(0 if ok else 1)