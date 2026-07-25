import mimetypes
import os

from django.db.models import Count, Q
from django.db.models.functions import Concat
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.pending.models import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    File,
    PendingInstructor,
)

from ..exceptions import AdminOpsError
from ..permissions import IsSuperAdmin
from ..serializers import (
    InstructorVerificationDetailSerializer,
    InstructorVerificationListSerializer,
    VerificationRejectSerializer,
)
from ..services import instructor_verification as service

_ORDERABLE_FIELDS = {"applied_at", "reviewed_at", "status"}


def _base_qs():
    return (
        PendingInstructor.objects.select_related("instructor_profile__user")
        .annotate(file_count=Count("files"))
    )


def _request_id(request) -> str:
    return request.headers.get("X-Request-ID", "")


class InstructorVerificationListView(ListAPIView):
    """GET /admin-api/v1/instructor-verifications/

    필터: ``status``, ``q``(이름/닉네임/이메일/대학 검색), ``ordering``.
    기본 PageNumberPagination(20/page).
    """

    permission_classes = [IsSuperAdmin]
    serializer_class = InstructorVerificationListSerializer

    def get_queryset(self):
        qs = _base_qs()
        params = self.request.query_params

        status_filter = params.get("status")
        if status_filter in PendingInstructor.Status.values:
            qs = qs.filter(status=status_filter)

        q = (params.get("q") or "").strip()
        if q:
            # 성(first_name)+이름(last_name) 을 이어붙인 실명으로도 검색 가능하게 합니다.
            qs = qs.annotate(
                _full_name=Concat(
                    "instructor_profile__user__first_name",
                    "instructor_profile__user__last_name",
                )
            ).filter(
                Q(_full_name__icontains=q)
                | Q(instructor_profile__user__first_name__icontains=q)
                | Q(instructor_profile__user__last_name__icontains=q)
                | Q(instructor_profile__user__user_name__icontains=q)
                | Q(instructor_profile__user__email__icontains=q)
                | Q(instructor_profile__university__icontains=q)
            )

        ordering = params.get("ordering", "-applied_at")
        if ordering.lstrip("-") in _ORDERABLE_FIELDS:
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by("-applied_at")
        return qs


class InstructorVerificationSummaryView(APIView):
    """GET /admin-api/v1/instructor-verifications/summary/

    상태별 건수 요약을 반환합니다. 예) {"PENDING": 3, "VERIFIED": 1, "SUSPENDED": 0, "total": 4}
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = PendingInstructor.objects.values("status").annotate(n=Count("id"))
        counts = {row["status"]: row["n"] for row in rows}
        data = {status: counts.get(status, 0) for status in PendingInstructor.Status.values}
        data["total"] = sum(data.values())
        return Response(data)


class InstructorVerificationDetailView(RetrieveAPIView):
    """GET /admin-api/v1/instructor-verifications/{pk}/"""

    permission_classes = [IsSuperAdmin]
    serializer_class = InstructorVerificationDetailSerializer

    def get_queryset(self):
        return _base_qs()


class InstructorVerificationApproveView(APIView):
    """POST /admin-api/v1/instructor-verifications/{pk}/approve/"""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        pending = get_object_or_404(PendingInstructor, pk=pk)
        try:
            service.approve(pending, admin=request.user, request_id=_request_id(request))
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        updated = _base_qs().get(pk=pk)
        return Response(InstructorVerificationDetailSerializer(updated).data)


class InstructorVerificationRejectView(APIView):
    """POST /admin-api/v1/instructor-verifications/{pk}/reject/ (사유 필수)"""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = VerificationRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pending = get_object_or_404(PendingInstructor, pk=pk)
        try:
            service.reject(
                pending,
                admin=request.user,
                reason=serializer.validated_data["reason"],
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        updated = _base_qs().get(pk=pk)
        return Response(InstructorVerificationDetailSerializer(updated).data)


class InstructorVerificationDocumentView(APIView):
    """GET /admin-api/v1/instructor-verifications/{pk}/documents/{file_id}/

    슈퍼관리자만 접근 가능한 보호 스트리밍 엔드포인트입니다. raw 미디어 URL 을
    노출하지 않고, PDF/JPG/PNG 만 ``Content-Disposition: inline`` 으로 제공합니다.

    Next BFF 는 Token 으로, Django Admin 은 세션으로 접근할 수 있도록 두 인증을
    모두 허용합니다(둘 다 IsSuperAdmin 검사를 거칩니다).
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk, file_id):
        try:
            document = File.objects.get(pk=file_id, pending_instructor_id=pk)
        except File.DoesNotExist as exc:
            raise Http404("Document not found") from exc

        name = document.pending_file.name
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise Http404("Unsupported document type")

        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        try:
            file_handle = document.pending_file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Document file missing") from exc

        return FileResponse(
            file_handle,
            as_attachment=False,
            filename=os.path.basename(name),
            content_type=content_type,
        )
