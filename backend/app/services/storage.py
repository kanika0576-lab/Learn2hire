"""File storage: S3 when DEMO_MODE=false, local disk otherwise."""

import os
import shutil
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings


def _s3():
    return boto3.client("s3", region_name=settings.aws_region)


def save_upload(course_id: str, filename: str, data: bytes) -> str:
    key = f"courses/{course_id}/{uuid.uuid4().hex[:8]}_{filename}"
    if settings.demo_mode:
        path = os.path.join(settings.upload_dir, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path
    try:
        _s3().put_object(Bucket=settings.s3_bucket, Key=key, Body=data)
        return key
    except (ClientError, BotoCoreError):
        path = os.path.join(settings.upload_dir, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path


def read_file(storage_key: str) -> bytes:
    if not settings.demo_mode and not os.path.exists(storage_key):
        try:
            resp = _s3().get_object(Bucket=settings.s3_bucket, Key=storage_key)
            return resp["Body"].read()
        except (ClientError, BotoCoreError):
            pass
    with open(storage_key, "rb") as f:
        return f.read()


def local_path(storage_key: str) -> str:
    """Return a filesystem path usable by local parsers, downloading from S3 if needed."""
    if os.path.exists(storage_key):
        return storage_key
    data = read_file(storage_key)
    path = os.path.join(settings.upload_dir, "cache", storage_key.replace("/", os.sep).replace("courses/", ""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def delete_file(storage_key: str) -> None:
    if settings.demo_mode or os.path.exists(storage_key):
        if os.path.exists(storage_key):
            os.remove(storage_key)
        return
    try:
        _s3().delete_object(Bucket=settings.s3_bucket, Key=storage_key)
    except (ClientError, BotoCoreError):
        pass


def clear_local() -> None:
    if os.path.isdir(settings.upload_dir):
        shutil.rmtree(settings.upload_dir, ignore_errors=True)
