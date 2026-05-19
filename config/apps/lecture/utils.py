from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


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
