"""Private S3 direct-upload helpers for lecture videos."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import boto3
from django.conf import settings
from django.core.cache import cache


MAX_VIDEO_BYTES = 1024 * 1024 * 1024
UPLOAD_POST_EXPIRES_SECONDS = 15 * 60
UPLOAD_SESSION_EXPIRES_SECONDS = 20 * 60
FINALIZATION_SLOT_COUNT = 2
FINALIZATION_SLOT_EXPIRES_SECONDS = 180


@dataclass(frozen=True)
class DirectUploadError(Exception):
    """A safe client-facing failure raised by the direct-upload workflow."""

    detail: str
    status_code: int


def _session_key(upload_id: str) -> str:
    """Return the cache key that owns [upload_id]."""
    return f"lecture-upload:session:{upload_id}"


def _completion_key(upload_id: str) -> str:
    """Return the short-lived completion mutex key for [upload_id]."""
    return f"lecture-upload:completion:{upload_id}"


def _slot_key(index: int) -> str:
    """Return the cache key for one bounded finalization slot."""
    return f"lecture-upload:finalization-slot:{index}"


def s3_client():
    """Return an S3 client authenticated by the instance role in production."""
    return boto3.client("s3", region_name=settings.AWS_S3_REGION_NAME)


def create_upload_session(*, user_id: int, filename: str, content_type: str, size: int) -> dict:
    """Create a short-lived S3 POST policy owned by [user_id]."""
    if content_type != "video/mp4" or not filename.lower().endswith(".mp4"):
        raise DirectUploadError("MP4 영상만 업로드할 수 있습니다.", 400)
    if size <= 0 or size > MAX_VIDEO_BYTES:
        raise DirectUploadError("영상 파일은 1GiB 이하만 업로드할 수 있습니다.", 400)

    upload_id = uuid4().hex
    object_key = f"lecture-uploads/{user_id}/{upload_id}.mp4"
    post = s3_client().generate_presigned_post(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=object_key,
        Fields={
            "Content-Type": content_type,
            "x-amz-server-side-encryption": "AES256",
        },
        Conditions=[
            {"key": object_key},
            {"Content-Type": content_type},
            {"x-amz-server-side-encryption": "AES256"},
            ["content-length-range", 1, MAX_VIDEO_BYTES],
        ],
        ExpiresIn=UPLOAD_POST_EXPIRES_SECONDS,
    )
    cache.set(
        _session_key(upload_id),
        {"user_id": user_id, "object_key": object_key, "size": size},
        timeout=UPLOAD_SESSION_EXPIRES_SECONDS,
    )
    return {
        "upload_id": upload_id,
        "url": post["url"],
        "fields": post["fields"],
        "expires_in": UPLOAD_POST_EXPIRES_SECONDS,
    }


def get_upload_session(*, upload_id: str, user_id: int) -> dict:
    """Return an unexpired session only when it belongs to [user_id]."""
    session = cache.get(_session_key(upload_id))
    if not session or session.get("user_id") != user_id:
        raise DirectUploadError("업로드 세션이 만료되었거나 접근할 수 없습니다.", 404)
    return session


def acquire_completion_lock(upload_id: str) -> str:
    """Prevent duplicate completion requests for one upload session."""
    token = uuid4().hex
    if not cache.add(_completion_key(upload_id), token, timeout=FINALIZATION_SLOT_EXPIRES_SECONDS):
        raise DirectUploadError("같은 영상의 등록 처리가 이미 진행 중입니다.", 409)
    return token


def release_completion_lock(upload_id: str, token: str) -> None:
    """Release a completion lock only when this caller still owns it."""
    key = _completion_key(upload_id)
    if cache.get(key) == token:
        cache.delete(key)


def acquire_finalization_slot() -> tuple[str, str]:
    """Reserve one of the bounded finalization slots or reject immediately."""
    token = uuid4().hex
    for index in range(FINALIZATION_SLOT_COUNT):
        key = _slot_key(index)
        if cache.add(key, token, timeout=FINALIZATION_SLOT_EXPIRES_SECONDS):
            return key, token
    raise DirectUploadError("다른 영상 등록을 처리 중입니다. 잠시 후 다시 시도해주세요.", 429)


def release_finalization_slot(key: str, token: str) -> None:
    """Release one finalization slot only when this caller owns it."""
    if cache.get(key) == token:
        cache.delete(key)


def verify_staging_object(session: dict) -> None:
    """Ensure the S3 object exists and exactly matches its signed session."""
    try:
        response = s3_client().head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=session["object_key"],
        )
    except Exception as exc:
        raise DirectUploadError("업로드한 영상을 찾을 수 없습니다. 다시 업로드해주세요.", 400) from exc

    if response.get("ContentLength") != session["size"]:
        raise DirectUploadError("업로드된 영상 크기가 올바르지 않습니다.", 400)
    if response.get("ContentType") != "video/mp4":
        raise DirectUploadError("업로드된 영상 형식이 올바르지 않습니다.", 400)


def create_staging_read_url(object_key: str) -> str:
    """Create a short-lived URL used only by server-side media probes."""
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key},
        ExpiresIn=120,
    )


def promote_staging_object(*, source_key: str, destination_key: str) -> None:
    """Copy a validated staging object into the permanent lecture prefix."""
    s3_client().copy_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=destination_key,
        CopySource={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": source_key},
        ContentType="video/mp4",
        MetadataDirective="REPLACE",
        ServerSideEncryption="AES256",
    )


def delete_object(object_key: str) -> None:
    """Delete one private S3 object without exposing its key to clients."""
    try:
        s3_client().delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=object_key)
    except Exception:
        # Lifecycle cleanup protects staging objects; cleanup must not mask the API error.
        return


def complete_upload_session(upload_id: str) -> None:
    """Remove a successfully finalized upload session from the cache."""
    cache.delete(_session_key(upload_id))
