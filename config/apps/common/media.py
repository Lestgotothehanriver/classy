import mimetypes
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils._os import safe_join


def _file_iterator(file_obj, start: int, length: int, chunk_size: int = 8192):
    file_obj.seek(start)
    remaining = length
    while remaining > 0:
        chunk = file_obj.read(min(chunk_size, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        yield chunk


def serve_media_with_range(request, path):
    """
    MEDIA_ROOT 파일을 HTTP Range 요청까지 지원해서 제공합니다.

    Android/iOS 동영상 플레이어는 MP4 재생 중 `Range: bytes=...` 요청을 자주
    사용하므로, 프로덕션 fallback 미디어 서빙에서도 206 응답을 지원해야 합니다.
    """
    try:
        full_path = safe_join(settings.MEDIA_ROOT, path)
    except ValueError as exc:
        raise Http404("Invalid media path") from exc

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("Media file not found")

    file_size = os.path.getsize(full_path)
    content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
    range_header = request.headers.get("Range")

    if not range_header:
        response = FileResponse(open(full_path, "rb"), content_type=content_type)
        response["Content-Length"] = str(file_size)
        response["Accept-Ranges"] = "bytes"
        return response

    if not range_header.startswith("bytes="):
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    byte_range = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
    start_text, _, end_text = byte_range.partition("-")

    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            suffix_length = int(end_text)
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
    except ValueError:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    end = min(end, file_size - 1)
    if start < 0 or start > end or start >= file_size:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    length = end - start + 1
    file_obj = open(full_path, "rb")

    if request.method == "HEAD":
        file_obj.close()
        response = HttpResponse(status=206, content_type=content_type)
    else:
        response = StreamingHttpResponse(
            _file_iterator(file_obj, start, length),
            status=206,
            content_type=content_type,
        )
        response._resource_closers.append(file_obj.close)

    response["Content-Length"] = str(length)
    response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    response["Accept-Ranges"] = "bytes"
    return response
