"""Seed a ready-to-demo account + course from learn2hire/sample/.

Creates:
  demo@learn2hire.dev / demo1234  — demo learner
  course "Intro to Data Structures — Lecture 1" with video + transcript + notes.pdf,
  ingested and indexed (knowledge base ready).

Run from backend/:  python seed.py     (idempotent - safe to re-run)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Course, Material, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import ingestion, storage  # noqa: E402

SAMPLE = os.environ.get(
    "L2H_SAMPLE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample"),
)
EMAIL = "demo@learn2hire.dev"
PASSWORD = "demo1234"

FILES = [
    ("lecture1.mp4", "video"),
    ("lecture1.vtt", "transcript"),
    ("notes.pdf", "pdf"),
]


def main() -> None:
    for f, _ in FILES:
        if not os.path.exists(os.path.join(SAMPLE, f)):
            raise SystemExit(f"missing sample file: {SAMPLE}\\{f} — run scripts/generate_sample.py first")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == EMAIL).first()
        if user is None:
            user = User(name="Demo Learner", email=EMAIL, password_hash=hash_password(PASSWORD))
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"created user {EMAIL} / {PASSWORD}")

        existing = (
            db.query(Course)
            .filter(Course.owner_id == user.id, Course.title.like("Intro to Data Structures%"))
            .first()
        )
        if existing and existing.status == "ready":
            print(f"course already ready: {existing.title} ({existing.id})")
            return

        course = existing or Course(
            owner_id=user.id,
            title="Intro to Data Structures — Lecture 1",
            description="Sample lecture: arrays, linked lists, stacks, queues, hash maps, trees, heaps, graphs and DP.",
        )
        if existing is None:
            db.add(course)
            db.commit()
            db.refresh(course)

        for filename, kind in FILES:
            already = db.query(Material).filter(Material.course_id == course.id, Material.filename == filename).first()
            if already:
                continue
            with open(os.path.join(SAMPLE, filename), "rb") as fh:
                data = fh.read()
            key = storage.save_upload(course.id, filename, data)
            db.add(Material(course_id=course.id, kind=kind, filename=filename, storage_key=key))
        db.commit()

        print("ingesting (transcribe/chunk/embed/index)...")
        db.refresh(course)
        result = ingestion.ingest_course(db, course)
        print(f"status={result['status']} chunks={result['chunks']} {result.get('message', '')}")

        if result["status"] == "ready":
            print(f"\nREADY — log in as {EMAIL} / {PASSWORD} and open the course.")
        else:
            print("\nIngestion did not complete — check the message above.")
    finally:
        db.close()


if __name__ == "__main__":
    # small retry guard against OneDrive/AV briefly locking the SQLite file
    for attempt in range(3):
        try:
            main()
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"retrying after transient error: {exc}")
            time.sleep(2)
