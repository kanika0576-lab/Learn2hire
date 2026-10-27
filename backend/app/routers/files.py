"""Stream material files back to the player with HTTP Range support
(so the browser can seek). Local disk in demo mode; S3 presigned redirect on AWS."""

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Course, Material
from app.security import user_from_token
from app.services import storage

router = APIRouter(prefix="/api/courses", tags=["files"])

CONTENT_TYPES = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
    "pdf": "application/pdf",
    "vtt": "text/vtt",
    "srt": "application/x-subrip",
    "txt": "text/plain",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
}


def _content_type(filename: str, storage_key: str = "") -> str:
    if storage_key.lower().endswith(".mp4") or filename.lower().endswith(".mp4"):
        return "video/mp4"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return CONTENT_TYPES.get(ext, "application/octet-stream")


@router.get("/{course_id}/materials/{material_id}/file")
def serve_material(
    course_id: str,
    material_id: str,
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    # The <video> tag cannot send a custom Authorization header, so allow ?token=
    # as a fallback for media URLs (demo-only convenience, same JWT).
    user = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        user = user_from_token(auth[7:], db)
    if user is None:
        user = user_from_token(token, db)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    course = db.get(Course, course_id)
    if course is None or course.owner_id != user.id:
        raise HTTPException(404, "Course not found")
    mat = db.get(Material, material_id)
    if mat is None or mat.course_id != course_id:
        raise HTTPException(404, "Material not found")

    # AWS mode: hand the browser a short-lived presigned URL
    if not settings.demo_mode and not os.path.exists(mat.storage_key):
        import boto3

        client = boto3.client("s3", region_name=settings.aws_region)
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": mat.storage_key},
            ExpiresIn=3600,
        )
        return Response(status_code=307, headers={"Location": url})

    path = storage.local_path(mat.storage_key)
    if not os.path.exists(path):
        raise HTTPException(404, "File not found on disk")

    file_size = os.path.getsize(path)
    content_type = _content_type(mat.filename, mat.storage_key)
    range_header = request.headers.get("range")

    if not range_header:
        with open(path, "rb") as f:
            body = f.read()
        return Response(
            content=body,
            media_type=content_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'inline; filename="{mat.filename}"',
                "Cache-Control": "no-store, max-age=0",
            },
        )

    m = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not m:
        raise HTTPException(416, "Malformed Range header")
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "":
        length = int(end_s or 0)
        start = max(file_size - length, 0)
        end = file_size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    if start >= file_size or end < start:
        raise HTTPException(416, "Range not satisfiable")
    end = min(end, file_size - 1)

    with open(path, "rb") as f:
        f.seek(start)
        chunk = f.read(end - start + 1)

    return Response(
        content=chunk,
        status_code=206,
        media_type=content_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{mat.filename}"',
            "Cache-Control": "no-store, max-age=0",
        },
    )
