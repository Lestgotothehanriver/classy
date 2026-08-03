"""신고 관리(adminops) API 뷰입니다.

정산/성사 뷰와 동일한 패턴을 따른다. 모두 슈퍼관리자 전용이며, 상태 전이(보류/종결/
제재)는 서비스 계층(``services/report.py``)에 위임하고 ``AdminOpsError`` 를
``{"error": ...}`` 응답으로 변환한다.

운영 단위는 **가해자(reported_user)** 다. 큐는 유저별 집계이고, 케이스 상세는 그
유저의 신고를 묶어 보여주며, 처리(resolve)는 그 유저의 미처리 신고를 일괄 종결한다.
증빙 이미지는 raw 미디어 URL 을 노출하지 않고 보호 스트리밍으로만 제공한다.
"""

import mimetypes
import os
import re

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.db.models.functions import Concat
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.accounts.models import UserSanction
from config.apps.report.models import Report, ReportSourceChoices, ReportStatusChoices

from ..exceptions import AdminOpsError
from ..permissions import IsSuperAdmin
from ..serializers.report import (
    ContentBlockSerializer,
    ReportCaseSerializer,
    ReportedUserListSerializer,
    ResolveCaseSerializer,
    SanctionInputSerializer,
)
from ..services import report as service

User = get_user_model()

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


def _stream_file(fieldfile, start: int, length: int, chunk: int = 8192):
    """FieldFile 의 [start, start+length) 구간을 청크 단위로 스트리밍한다."""
    handle = fieldfile.open("rb")
    try:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            data = handle.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        handle.close()

_OPEN_STATUSES = [ReportStatusChoices.PENDING, ReportStatusChoices.IN_REVIEW]
_STATUS_VALUES = set(ReportStatusChoices.values)
_SOURCE_VALUES = set(ReportSourceChoices.values)
_ORDERABLE_FIELDS = {
    "last_reported_at",
    "pending_count",
    "total_count",
    "effective_count",
}


def _request_id(request) -> str:
    return request.headers.get("X-Request-ID", "")


class ReportedUserListView(ListAPIView):
    """GET /admin-api/v1/reports/

    피신고 유저(가해자) 집계 큐. 필터: ``status``(그 상태의 신고 보유),
    ``source``(그 맥락의 신고 보유), ``q``(실명/닉네임/이메일), ``ordering``.
    기본 PageNumberPagination(20/page).
    """

    permission_classes = [IsSuperAdmin]
    serializer_class = ReportedUserListSerializer

    def get_queryset(self):
        params = self.request.query_params
        qs = (
            User.objects.filter(reports_received__isnull=False)
            .distinct()
            .annotate(
                pending_count=Count(
                    "reports_received",
                    filter=Q(reports_received__status__in=_OPEN_STATUSES),
                    distinct=True,
                ),
                total_count=Count("reports_received", distinct=True),
                effective_count=Count(
                    "reports_received",
                    filter=Q(reports_received__status=ReportStatusChoices.RESOLVED),
                    distinct=True,
                ),
                unique_reporters=Count("reports_received__reporter", distinct=True),
                active_sanction_count=Count(
                    "sanctions", filter=Q(sanctions__is_active=True), distinct=True
                ),
                last_reported_at=Max("reports_received__created_at"),
            )
        )

        # 상태/맥락 필터는 집계 왜곡을 피하려 Exists 서브쿼리로 '보유 여부'만 건다.
        status_filter = params.get("status")
        if status_filter in _STATUS_VALUES:
            qs = qs.filter(
                Exists(
                    Report.objects.filter(
                        reported_user=OuterRef("pk"), status=status_filter
                    )
                )
            )

        source_filter = params.get("source")
        if source_filter in _SOURCE_VALUES:
            qs = qs.filter(
                Exists(
                    Report.objects.filter(
                        reported_user=OuterRef("pk"), source=source_filter
                    )
                )
            )

        q = (params.get("q") or "").strip()
        if q:
            qs = qs.annotate(_full_name=Concat("last_name", "first_name")).filter(
                Q(_full_name__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(user_name__icontains=q)
                | Q(email__icontains=q)
            )

        ordering = params.get("ordering", "-last_reported_at")
        if ordering.lstrip("-") in _ORDERABLE_FIELDS:
            return qs.order_by(ordering, "-pk")
        return qs.order_by("-last_reported_at", "-pk")


class ReportedUserSummaryView(APIView):
    """GET /admin-api/v1/reports/summary/

    신고 상태별 건수 + 피신고 유저 수를 반환한다.
    예) {"pending": 5, "in_review": 1, "resolved": 3, "dismissed": 2,
         "total": 11, "reported_users": 7}
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = Report.objects.values("status").annotate(n=Count("id"))
        counts = {row["status"]: row["n"] for row in rows}
        data = {value: counts.get(value, 0) for value in _STATUS_VALUES}
        data["total"] = sum(data.values())
        data["reported_users"] = (
            User.objects.filter(reports_received__isnull=False).distinct().count()
        )
        return Response(data)


class ReportCaseDetailView(APIView):
    """GET /admin-api/v1/reports/users/{user_id}/ — 가해자 통합 케이스."""

    permission_classes = [IsSuperAdmin]

    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        return Response(ReportCaseSerializer(user).data)


class ReportCaseResolveView(APIView):
    """POST /admin-api/v1/reports/users/{user_id}/resolve/

    그 유저의 미처리 신고를 일괄 종결(+선택 제재)한다.
    body: {"outcome": "resolved|dismissed", "reason": "", "sanction": {...}?}
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        serializer = ResolveCaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service.resolve_case(
                user,
                admin=request.user,
                outcome=serializer.validated_data["outcome"],
                reason=serializer.validated_data.get("reason", ""),
                sanction=serializer.validated_data.get("sanction"),
                content_actions=serializer.validated_data.get("content_actions"),
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        return Response(ReportCaseSerializer(user).data)


class ReportContentActionView(APIView):
    """POST /admin-api/v1/reports/users/{user_id}/content/

    개별 콘텐츠를 즉시 차단/해제한다(케이스 종결과 별개의 인라인 조치).
    body: {"content_type": "lecture|comment|tutoring_post", "object_id": 1, "action": "block|unblock"}
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        serializer = ContentBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = service.resolve_content(
                serializer.validated_data["content_type"],
                serializer.validated_data["object_id"],
            )
            if serializer.validated_data["action"] == "unblock":
                service.unblock_content(obj, admin=request.user, request_id=_request_id(request))
            else:
                service.block_content(obj, admin=request.user, request_id=_request_id(request))
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        return Response(ReportCaseSerializer(user).data)


class LectureReviewStreamView(APIView):
    """GET /admin-api/v1/reports/lectures/{lecture_id}/review-stream/

    신고 검토용 영상 보호 스트리밍(Range 지원). 앱의 대여/차단 로직을 우회해 관리자가
    판정을 위해 원본을 재생할 수 있게 한다. 슈퍼관리자 전용.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, lecture_id):
        from config.apps.lecture.models import Lecture

        lecture = get_object_or_404(Lecture, pk=lecture_id)
        if not lecture.video:
            raise Http404("No video")
        video = lecture.video
        try:
            size = video.size
        except (FileNotFoundError, OSError) as exc:
            raise Http404("Video file missing") from exc

        content_type = mimetypes.guess_type(video.name)[0] or "video/mp4"
        match = _RANGE_RE.match(request.headers.get("Range", "") or "")
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                resp = HttpResponse(status=416)
                resp["Content-Range"] = f"bytes */{size}"
                return resp
            length = end - start + 1
            resp = StreamingHttpResponse(
                _stream_file(video, start, length), status=206, content_type=content_type
            )
            resp["Content-Range"] = f"bytes {start}-{end}/{size}"
            resp["Content-Length"] = str(length)
        else:
            resp = StreamingHttpResponse(
                _stream_file(video, 0, size), content_type=content_type
            )
            resp["Content-Length"] = str(size)
        resp["Accept-Ranges"] = "bytes"
        return resp


class ReportSanctionView(APIView):
    """POST /admin-api/v1/reports/users/{user_id}/sanction/ — 단독 제재 발급."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        serializer = SanctionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service.issue_sanction(
                user,
                admin=request.user,
                sanction_type=serializer.validated_data["type"],
                reason=serializer.validated_data.get("reason", ""),
                expires_at=serializer.validated_data.get("expires_at"),
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        return Response(ReportCaseSerializer(user).data)


class ReportLiftSanctionView(APIView):
    """POST /admin-api/v1/reports/sanctions/{sanction_id}/lift/ — 제재 해제."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, sanction_id):
        sanction = get_object_or_404(UserSanction, pk=sanction_id)
        try:
            service.lift_sanction(
                sanction,
                admin=request.user,
                reason=request.data.get("reason", ""),
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        return Response(ReportCaseSerializer(sanction.target_user).data)


class ReportInReviewView(APIView):
    """POST /admin-api/v1/reports/{pk}/in-review/ — 개별 신고를 보류로 전환."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        try:
            service.set_in_review(
                report, admin=request.user, request_id=_request_id(request)
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        return Response(ReportCaseSerializer(report.reported_user).data)


class ReportEvidenceView(APIView):
    """GET /admin-api/v1/reports/{pk}/evidence/

    슈퍼관리자 전용 보호 스트리밍. raw 미디어 URL 을 노출하지 않고 증빙 이미지를
    ``Content-Disposition: inline`` 으로 제공한다. Next BFF(Token)와 Django
    Admin(세션) 접근을 모두 허용한다.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        if not report.evidence_image:
            raise Http404("No evidence image")

        name = report.evidence_image.name
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        try:
            file_handle = report.evidence_image.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Evidence file missing") from exc

        return FileResponse(
            file_handle,
            as_attachment=False,
            filename=os.path.basename(name),
            content_type=content_type,
        )
