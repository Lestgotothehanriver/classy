from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from django.core.files import File


VIDEO_PROBE_TIMEOUT_SECONDS = 10
SAMPLE_PREVIEW_TIMEOUT_SECONDS = 60


def resolve_video_path(video_file) -> str | None:
    if video_file is None:
        return None

    if isinstance(video_file, (str, Path)):
        return str(video_file)

    temporary_file_path = getattr(video_file, "temporary_file_path", None)
    if callable(temporary_file_path):
        try:
            return temporary_file_path()
        except Exception:
            pass

    try:
        path = getattr(video_file, "path", None)
    except NotImplementedError:
        # Remote storage has no filesystem path. Uploads are processed before save.
        return None
    if path:
        return str(path)

    # Converted videos are django File wrappers with a display name (e.g. x.mp4).
    # ffprobe needs the temporary file's actual path before the upload to S3.
    wrapped_file = getattr(video_file, 'file', None)
    wrapped_path = getattr(wrapped_file, 'name', None)
    if isinstance(wrapped_path, (str, Path)) and Path(wrapped_path).is_file():
        return str(wrapped_path)

    return None


@contextmanager
def materialize_video_path(video_file):
    """Yield a local path for uploads and storage-backed FieldFiles alike."""
    existing_path = resolve_video_path(video_file)
    if existing_path:
        yield existing_path
        return

    suffix = Path(getattr(video_file, "name", "lecture.mp4")).suffix or ".mp4"
    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            opener = getattr(video_file, "open", None)
            if callable(opener):
                opener("rb")
            shutil.copyfileobj(video_file, temp_file)
        yield str(temp_path)
    finally:
        closer = getattr(video_file, "close", None)
        if callable(closer):
            closer()
        temp_path.unlink(missing_ok=True)


def extract_video_duration_seconds(video_file) -> int | None:
    inspection = inspect_video_file(video_file)
    return inspection["duration"] if inspection else None


def calculate_sample_preview_duration_seconds(video_duration: int) -> int:
    """Return the policy duration for a paid lecture sample preview."""
    if video_duration <= 0:
        raise ValueError("영상 길이를 확인할 수 없습니다.")
    if video_duration < 5 * 60:
        return max(1, int(video_duration * 0.2))
    return 60


def create_sample_preview(video_file, preview_duration: int) -> tuple[File, Callable[[], None]]:
    """Create an exact H.264/AAC MP4 preview from the start of [video_file].

    The returned cleanup callback must run after Django storage has consumed the
    file. A processing failure is intentional: a paid lecture must never be
    published without its required sample preview.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path or preview_duration <= 0:
        raise ValueError("미리보기 영상을 생성할 수 없습니다.")

    source_name = Path(getattr(video_file, "name", "lecture.mp4")).stem
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".mp4", prefix=f"{source_name}-sample-", delete=False
    )
    temp_path = Path(temp_file.name)
    temp_file.close()
    try:
        with materialize_video_path(video_file) as video_path:
            subprocess.run(
                [
                    ffmpeg_path, "-y", "-i", video_path, "-t", str(preview_duration),
                    "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    str(temp_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=SAMPLE_PREVIEW_TIMEOUT_SECONDS,
            )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        temp_path.unlink(missing_ok=True)
        raise ValueError("미리보기 영상을 생성할 수 없습니다.") from exc

    preview = File(temp_path.open("rb"), name=f"{source_name}-sample.mp4")

    def cleanup() -> None:
        preview.close()
        temp_path.unlink(missing_ok=True)

    return preview, cleanup


def _inspect_video_source(source: str) -> dict[str, object] | None:
    """Return the container, primary streams, and duration for [source]."""
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None

    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type,codec_name",
                "-of",
                "json",
                source,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=VIDEO_PROBE_TIMEOUT_SECONDS,
        )
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        format_data = payload.get("format", {})
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
    ):
        return None

    def codec_for(stream_type: str) -> str | None:
        for stream in streams:
            if stream.get("codec_type") == stream_type:
                codec = stream.get("codec_name")
                return codec.lower() if isinstance(codec, str) else None
        return None

    try:
        duration = int(float(format_data.get("duration", "0")))
    except (TypeError, ValueError):
        return None

    if duration <= 0:
        return None

    format_names = format_data.get("format_name", "")
    return {
        "container": "mp4" if "mp4" in str(format_names).split(",") else None,
        "video": codec_for("video"),
        "audio": codec_for("audio"),
        "duration": duration,
    }


def inspect_video_file(video_file) -> dict[str, object] | None:
    """Inspect an uploaded or storage-backed video without mutating it."""
    try:
        with materialize_video_path(video_file) as video_path:
            return _inspect_video_source(video_path)
    except OSError:
        return None


def inspect_video_url(url: str) -> dict[str, object] | None:
    """Inspect a short-lived signed media URL without logging the URL."""
    return _inspect_video_source(url)


def probe_video_codecs(video_file) -> dict[str, str | None]:
    """
    업로드된 영상의 대표 비디오/오디오 코덱을 확인합니다.

    Returns:
        dict: {"video": "h264", "audio": "aac"} 형태의 코덱 정보.
    """
    inspection = inspect_video_file(video_file)
    if not inspection:
        return {"video": None, "audio": None}
    return {
        "video": inspection["video"],
        "audio": inspection["audio"],
    }


def is_mobile_playback_compatible(video_file) -> bool:
    """
    앱 내 재생에 안전한 H.264/AAC 계열 MP4인지 확인합니다.

    HEVC(H.265)는 일부 Android 기기 또는 media_kit/MediaCodec 조합에서 검은 화면,
    무한 버퍼링, 디코더 실패가 발생할 수 있으므로 업로드 단계에서 거절합니다.
    """
    inspection = inspect_video_file(video_file)
    return bool(
        inspection
        and inspection["container"] == "mp4"
        and inspection["video"] == "h264"
        and inspection["audio"] == "aac"
    )


def is_supported_lecture_video(video_file) -> bool:
    """Return whether [video_file] satisfies the lecture playback contract."""
    return is_mobile_playback_compatible(video_file)


def is_supported_lecture_video_url(url: str) -> tuple[bool, int | None]:
    """Return whether a signed source [url] is supported and its duration."""
    inspection = inspect_video_url(url)
    if not inspection:
        return False, None
    is_supported = (
        inspection["container"] == "mp4"
        and inspection["video"] == "h264"
        and inspection["audio"] == "aac"
    )
    return is_supported, inspection["duration"] if is_supported else None


def _create_stream_copy_sample_preview(
    source: str,
    source_name: str,
    preview_duration: int,
) -> tuple[File, Callable[[], None]]:
    """Create a bounded MP4 preview without re-encoding [source]."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path or preview_duration <= 0:
        raise ValueError("미리보기 영상을 생성할 수 없습니다.")

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".mp4", prefix=f"{source_name}-sample-", delete=False
    )
    temp_path = Path(temp_file.name)
    temp_file.close()
    try:
        subprocess.run(
            [
                ffmpeg_path, "-y", "-i", source, "-t", str(preview_duration),
                "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                "-movflags", "+faststart", str(temp_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=SAMPLE_PREVIEW_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        temp_path.unlink(missing_ok=True)
        raise ValueError("미리보기 영상을 생성할 수 없습니다.") from exc

    preview = File(temp_path.open("rb"), name=f"{source_name}-sample.mp4")

    def cleanup() -> None:
        preview.close()
        temp_path.unlink(missing_ok=True)

    return preview, cleanup


def create_stream_copy_sample_preview(
    video_file,
    preview_duration: int,
) -> tuple[File, Callable[[], None]]:
    """Create a preview from a validated local or storage-backed video."""
    source_name = Path(getattr(video_file, "name", "lecture.mp4")).stem
    with materialize_video_path(video_file) as video_path:
        return _create_stream_copy_sample_preview(video_path, source_name, preview_duration)


def create_stream_copy_sample_preview_from_url(
    url: str,
    preview_duration: int,
) -> tuple[File, Callable[[], None]]:
    """Create a preview directly from a short-lived signed S3 [url]."""
    return _create_stream_copy_sample_preview(url, "lecture", preview_duration)
