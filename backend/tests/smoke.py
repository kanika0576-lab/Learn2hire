"""End-to-end smoke test for the Learn2Hire backend.

Covers: register -> course -> upload (video+vtt+pdf) -> ingest ->
time-gated /ask (including the no-spoiler check) -> chat history ->
quiz generate/submit -> interview start/answer/scorecard.

Run:  python -m tests.smoke        (from backend/)
"""

import io
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"

VTT = """WEBVTT

00:00.000 --> 00:00:12.000
Welcome to Intro to Data Structures. Today we start with arrays.

00:00:12.000 --> 00:00:30.000
An array stores elements in contiguous memory, giving O(1) index access.

00:00:30.000 --> 00:01:00.000
Linked lists trade that for O(1) insertion at the head, but lose random access.

00:01:00.000 --> 00:01:30.000
Stacks are LIFO structures. Push adds to the top, pop removes from the top.

00:01:30.000 --> 00:02:00.000
Queues are FIFO. Enqueue adds at the rear, dequeue removes from the front.

00:02:00.000 --> 00:02:40.000
Hash maps give average O(1) lookup by hashing keys into buckets.

00:02:40.000 --> 00:03:20.000
Trees keep data sorted. A binary search tree supports O(log n) search when balanced.

00:03:20.000 --> 00:04:00.000
Heaps implement priority queues, with O(log n) extract-min.

00:04:00.000 --> 00:04:40.000
Graphs are collections of vertices and edges, traversed with BFS or DFS.

00:04:40.000 --> 00:05:20.000
Dynamic programming caches subproblem results to avoid recomputation.

00:05:20.000 --> 00:06:00.000
In the next lesson we implement a red-black tree from scratch.
"""


def make_pdf(pages: list[str]) -> bytes:
    """Minimal single/multi-page PDF with Helvetica text (no external deps)."""
    objs: list[bytes] = []
    kids = " ".join(f"{5 + i * 2} 0 R" for i in range(len(pages)))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs.append(b"<< >>")
    for i, text in enumerate(pages):
        content_id = 6 + i * 2
        page_id = 5 + i * 2
        lines = text.split("\n")
        stream_lines = ["BT /F1 12 Tf 50 780 Td 16 TL"]
        for j, ln in enumerate(lines):
            safe = ln.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            stream_lines.append(f"({safe}) Tj T*" if j else f"({safe}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    )
    return out.getvalue()


def check(label: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        sys.exit(1)


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=300.0)

    r = c.get("/api/health")
    check("health", r.status_code == 200 and r.json()["status"] == "ok", r.text[:120])

    email = f"smoke_{int(time.time())}@demo.dev"
    r = c.post("/api/auth/register", json={"name": "Smoke Tester", "email": email, "password": "secret12"})
    check("register", r.status_code == 200, r.text[:160])
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    r = c.get("/api/auth/me", headers=H)
    check("me", r.status_code == 200 and r.json()["email"] == email)

    r = c.post("/api/courses", headers=H, json={"title": "Intro to DSA", "description": "smoke test"})
    check("create course", r.status_code == 200, r.text[:160])
    course_id = r.json()["id"]

    def upload(name: str, data: bytes):
        r = c.post(
            f"/api/courses/{course_id}/materials",
            headers=H,
            files={"file": (name, data, "application/octet-stream")},
        )
        check(f"upload {name}", r.status_code == 200, r.text[:160])

    upload("lecture1.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    upload("lecture1.vtt", VTT.encode())
    upload("notes.pdf", make_pdf([
        "Course Notes - Arrays and Linked Lists\nAn array stores elements in contiguous memory.\nIndex access is O(1).",
        "Stacks and Queues\nA stack is LIFO: push and pop operate on the top.\nA queue is FIFO: enqueue at rear, dequeue at front.",
        "Hash Maps\nHash maps average O(1) lookup by hashing keys into buckets.",
    ]))

    r = c.post(f"/api/courses/{course_id}/ingest", headers=H)
    check("ingest start", r.status_code == 200, r.text[:160])

    status = {}
    for _ in range(60):
        time.sleep(1)
        status = c.get(f"/api/courses/{course_id}/status", headers=H).json()
        if status["status"] in ("ready", "error"):
            break
    check("ingest completes", status["status"] == "ready", json.dumps(status)[:300])
    check("chunks indexed", status.get("chunks", 0) >= 5, f"chunks={status.get('chunks')}")

    # 1) question about content within watched time
    r = c.post("/api/ask", headers=H, json={"course_id": course_id, "question": "What is a stack?", "video_time": 95})
    check("ask in-material", r.status_code == 200, r.text[:300])
    a = r.json()
    check("ask has sources", len(a["sources"]) >= 1, json.dumps(a["sources"][:2]))
    check("answer mentions stack", "stack" in a["answer"].lower(), a["answer"][:160])

    # 2) no-spoiler: ask about the last-lesson topic before its timestamp
    r = c.post("/api/ask", headers=H, json={"course_id": course_id, "question": "Explain red-black trees", "video_time": 30})
    check("ask covered-later", r.status_code == 200, r.text[:300])
    a2 = r.json()
    check(
        "no spoiler (no red-black source at t=30s)",
        a2["covered_later"] or not any(
            s["type"] == "video" and (s["start_time"] or 0) > 30 for s in a2["sources"]
        ),
        json.dumps({"covered_later": a2["covered_later"], "sources": a2["sources"]})[:300],
    )

    # 3) honest not-in-material
    r = c.post("/api/ask", headers=H, json={"course_id": course_id, "question": "What is the capital of France?", "video_time": 100})
    check("ask not-in-material", r.status_code == 200 and r.json()["in_material"] is False, r.text[:200])

    # 4) chat history
    r = c.get(f"/api/courses/{course_id}/chat", headers=H)
    check("chat history", r.status_code == 200 and len(r.json()) >= 6, f"n={len(r.json()) if r.status_code==200 else '?'}")

    # 5) quiz
    r = c.post("/api/quiz/generate", headers=H, json={"course_id": course_id, "video_time": 200, "n_questions": 4})
    check("quiz generate", r.status_code == 200, r.text[:300])
    questions = r.json()["questions"]
    check("quiz has questions", len(questions) >= 2, f"n={len(questions)}")
    answers = {q["id"]: q["correct_index"] for q in questions}
    r = c.post("/api/quiz/submit", headers=H, json={"course_id": course_id, "answers": answers})
    check("quiz submit all-correct", r.status_code == 200 and r.json()["score"] == r.json()["total"], r.text[:200])
    wrong = {questions[0]["id"]: (questions[0]["correct_index"] + 1) % 4}
    r = c.post("/api/quiz/submit", headers=H, json={"course_id": course_id, "answers": wrong})
    check("quiz partial grading", r.status_code == 200 and r.json()["score"] < r.json()["total"], r.text[:200])

    # 6) interview loop
    r = c.post("/api/interview/start", headers=H, json={"course_id": course_id})
    check("interview start", r.status_code == 200, r.text[:300])
    sess = r.json()
    sid = sess["session_id"]
    check("first question asked", len(sess["current_question"]) > 10, sess["current_question"][:120])

    final_card = {}
    for turn in range(8):
        ans = (
            "Arrays store elements in contiguous memory with O(1) index access; "
            "a stack is LIFO where push and pop act on the top. I would use an array when "
            "I need fast random access, and a linked list when I need frequent insertion."
        )
        r = c.post("/api/interview/answer", headers=H, json={"session_id": sid, "answer": ans})
        check(f"interview turn {turn + 1}", r.status_code == 200, r.text[:300])
        data = r.json()
        check("evaluation present", isinstance(data.get("evaluation"), dict) and "technical_accuracy" in data["evaluation"])
        if data["status"] == "completed":
            final_card = data["scorecard"]
            break
        time.sleep(0.2)

    check("interview completed with scorecard", bool(final_card), json.dumps(final_card)[:300])
    check(
        "scorecard explainable",
        all(k in final_card for k in ("technical_accuracy", "communication", "relevance", "overall", "explanation")),
        json.dumps({k: final_card.get(k) for k in ("overall", "grade")}),
    )

    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
