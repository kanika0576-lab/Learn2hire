import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
import io
import zipfile

from app.database import get_db
from app.models import Course, Material, User
from app.schemas import CourseCreate, CourseOut
from app.security import get_current_user
from app.services import ingestion, storage
from app.services.notes import build as build_notes, cache_notes, get_notes

router = APIRouter(prefix="/api/courses", tags=["courses"])

MAX_SIZE = 400 * 1024 * 1024


def _kind_for(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in (
        "mp4", "mov", "mkv", "webm", "m4v", "avi", "avif", "flv", "ts", "mts", "m2ts", "3gp", "gif", "webp",
    ):
        # browser-hostile containers are converted to mp4 during ingestion
        return "video"
    if ext == "pdf":
        return "pdf"
    if ext in ("pptx", "ppt"):
        return "slides"
    if ext in ("vtt", "srt", "txt"):
        return "transcript"
    raise HTTPException(415, f"Unsupported file type '.{ext}'. Use video (mp4/webm/mkv/gif/avif…), pdf, pptx, vtt, srt or txt.")


@router.post("", response_model=CourseOut)
def create_course(body: CourseCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = Course(owner_id=user.id, title=body.title.strip(), description=body.description.strip())
    db.add(course)
    db.commit()
    db.refresh(course)
    return _out(course)


@router.get("")
def list_courses(user=Depends(get_current_user), db: Session = Depends(get_db)):
    courses = (
        db.query(Course).filter(Course.owner_id == user.id).order_by(Course.created_at.desc()).all()
    )
    return [_out(c, with_counts=True) for c in courses]


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(course_id, user, db)
    return _out(course)


@router.post("/{course_id}/materials", response_model=CourseOut)
async def upload_material(
    course_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    course = _owned(course_id, user, db)
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(413, "File too large (max 400 MB)")
    if not data:
        raise HTTPException(400, "Empty file")

    # A ZIP is one drop but many files — unpack and register every entry.
    if (file.filename or "").lower().endswith(".zip"):
        names: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                    if not name or name.startswith(".") or "/__MACOSX/" in info.filename:
                        continue
                    _kind_for(name)  # reject unsupported extensions outright
                    payload = zf.read(info)
                    if not payload:
                        continue
                    key = storage.save_upload(course.id, name, payload)
                    db.add(
                        Material(
                            course_id=course.id,
                            kind=_kind_for(name),
                            filename=name,
                            storage_key=key,
                            status="uploaded",
                        )
                    )
                    names.append(name)
        except zipfile.BadZipFile:
            raise HTTPException(400, "This file is not a valid ZIP archive.")
        if not names:
            raise HTTPException(400, "The ZIP contains no usable files (video, captions, PDF, slides…).")
        db.commit()
        if course.status in ("ready", "error"):
            course.status = "created"
        db.commit()
        db.refresh(course)
        return _out(course)

    kind = _kind_for(file.filename or "file")
    key = storage.save_upload(course.id, file.filename or "upload", data)
    mat = Material(
        course_id=course.id,
        kind=kind,
        filename=file.filename or "upload",
        storage_key=key,
        status="uploaded",
    )
    db.add(mat)
    if course.status in ("ready", "error"):
        course.status = "created"
    db.commit()
    db.refresh(course)
    return _out(course)


@router.post("/{course_id}/ingest")
def ingest(
    course_id: str,
    background: BackgroundTasks,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    course = _owned(course_id, user, db)
    if not course.materials:
        raise HTTPException(400, "Upload at least one material first")

    def _run():
        from app.database import SessionLocal

        session = SessionLocal()
        try:
            c = session.get(Course, course_id)
            if c:
                ingestion.ingest_course(session, c)
        finally:
            session.close()

    course.status = "ingesting"
    course.error = ""
    db.commit()
    background.add_task(_run)
    return {"status": "ingesting", "message": "Ingestion started"}


@router.get("/{course_id}/status")
def status(course_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(course_id, user, db)
    from app.services.index import get_index

    return {
        "status": course.status,
        "error": course.error,
        "chunks": get_index().count(course.id) if course.status in ("ready", "ingesting", "error") else 0,
        "materials": [
            {"id": m.id, "filename": m.filename, "kind": m.kind, "status": m.status} for m in course.materials
        ],
    }


@router.delete("/{course_id}")
def delete_course(course_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(course_id, user, db)
    for m in course.materials:
        storage.delete_file(m.storage_key)
    ingestion.delete_course_data(course.id)
    db.delete(course)
    db.commit()
    return {"deleted": course_id}


# ----------------------------- study notes -----------------------------

_NOTES_READY = "Build the knowledge base first."


@router.get("/{course_id}/notes")
def read_notes(course_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(course_id, user, db)
    if course.status != "ready":
        raise HTTPException(409, _NOTES_READY)
    cached = get_notes(course_id)
    if cached:
        return cached
    built = build_notes(course.id, course.title)
    cache_notes(course_id, built)
    return built


@router.post("/{course_id}/notes")
def rebuild_notes(course_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(course_id, user, db)
    if course.status != "ready":
        raise HTTPException(409, _NOTES_READY)
    built = build_notes(course.id, course.title)
    cache_notes(course_id, built)
    return built


def _owned(course_id: str, user: User, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if course.owner_id != user.id:
        raise HTTPException(403, "Not your course")
    return course


def _out(course: Course, with_counts: bool = False) -> dict:
    payload = {
        "id": course.id,
        "title": course.title,
        "description": course.description or "",
        "status": course.status,
        "error": course.error or "",
        "materials": [],
    }
    payload["materials"] = [
        {"id": m.id, "filename": m.filename, "kind": m.kind, "status": m.status, "duration": m.duration_seconds}
        for m in course.materials
    ]
    if with_counts:
        from app.services.index import get_index

        try:
            payload["chunks"] = get_index().count(course.id)
        except Exception:
            payload["chunks"] = 0
    return payload
