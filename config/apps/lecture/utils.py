from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from django.core.files import File


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

    path = getattr(video_file, "path", None)
    if path:
        return str(path)

    return None


def extract_video_duration_seconds(video_file) -> int | None:
    video_path = resolve_video_path(video_file)
    if not video_path:
        return None

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
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(result.stdout.strip())
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None

    if duration <= 0:
        return None

    return round(duration)


def probe_video_codecs(video_file) -> dict[str, str | None]:
    """
    업로드된 영상의 대표 비디오/오디오 코덱을 확인합니다.

    Returns:
        dict: {"video": "h264", "audio": "aac"} 형태의 코덱 정보.
    """
    video_path = resolve_video_path(video_file)
    ffprobe_path = shutil.which("ffprobe")
    if not video_path or not ffprobe_path:
        return {"video": None, "audio": None}

    def _probe(stream_selector: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v",
                    "error",
                    "-select_streams",
                    stream_selector,
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=nokey=1:noprint_wrappers=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None

        codec = result.stdout.strip().splitlines()
        return codec[0].strip().lower() if codec else None

    return {
        "video": _probe("v:0"),
        "audio": _probe("a:0"),
    }


def is_mobile_playback_compatible(video_file) -> bool:
    """
    앱 내 재생에 안전한 H.264/AAC 계열 MP4인지 확인합니다.

    HEVC(H.265)는 일부 Android 기기 또는 media_kit/MediaCodec 조합에서 검은 화면,
    무한 버퍼링, 디코더 실패가 발생할 수 있어 업로드 저장 전에 H.264로 정규화합니다.
    """
    codecs = probe_video_codecs(video_file)
    video_codec = codecs["video"]
    audio_codec = codecs["audio"]
    return video_codec == "h264" and audio_codec in {None, "aac", "mp3"}


def transcode_video_for_mobile_playback(
    video_file,
) -> tuple[object, Callable[[], None] | None]:
    """
    모바일 재생 호환성을 위해 영상을 H.264/AAC MP4로 변환합니다.

    ffmpeg가 없거나 이미 호환 코덱이면 원본을 그대로 반환합니다. 변환된 임시 파일은
    serializer가 모델 저장을 끝낸 뒤 cleanup 콜백으로 정리해야 합니다.
    """
    video_path = resolve_video_path(video_file)
    ffmpeg_path = shutil.which("ffmpeg")
    if (
        not video_path
        or not ffmpeg_path
        or is_mobile_playback_compatible(video_file)
    ):
        return video_file, None

    source_name = Path(getattr(video_file, "name", "lecture.mp4")).stem
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".mp4",
        prefix=f"{source_name}-h264-",
        delete=False,
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                video_path,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        temp_path.unlink(missing_ok=True)
        return video_file, None

    transcoded = File(temp_path.open("rb"), name=f"{source_name}.mp4")

    def cleanup():
        transcoded.close()
        temp_path.unlink(missing_ok=True)

    return transcoded, cleanup


def normalize_field_file_for_mobile_playback(field_file) -> bool:
    """
    기존 FileField 파일을 모바일 재생 호환 MP4로 교체합니다.

    Returns:
        bool: 파일이 변환되어 교체되었으면 True.
    """
    playable_video, cleanup = transcode_video_for_mobile_playback(field_file)
    if cleanup is None or playable_video is field_file:
        return False

    try:
        field_file.save(playable_video.name, playable_video, save=False)
        return True
    finally:
        cleanup()
