"""성사등록(과외 성사) 관리 API 뷰입니다.

정산(settlement) 뷰와 동일한 패턴을 따릅니다. 모두 슈퍼관리자 전용이며, 상태 전이
(수수료 확인/반려)는 서비스 계층에 위임하고 ``AdminOpsError`` 를 ``{"error": ...}``
응답으로 변환합니다. 증빙 파일은 raw 미디어 URL 을 노출하지 않고 보호 스트리밍
엔드포인트로만 제공합니다.
"""

import mimetypes
import os

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.db.models.functions import Concat
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.tutoring.models import (
    CommissionInvoice,
    TutoringRegistration,
    TutoringResource,
    TutoringResourceFile,
)

from ..exceptions import AdminOpsError
from ..permissions import IsSuperAdmin
from ..serializers import (
    RejectFeeSerializer,
    TutoringRegistrationDetailSerializer,
    TutoringRegistrationListSerializer,
)
from ..services import tutoring_registration as service

_CONTRACT_VALUES = set(TutoringRegistration.ContractStatus.values)
_VALIDATION_VALUES = set(TutoringRegistration.AttributeValidationStatus.values)
_FEE_VALUES = {"PENDING", "AWAITING_CONFIRMATION", "PAID", "FAILED"}
_ORDERABLE_FIELDS = {"created_at", "updated_at", "start_date", "commission_amount"}
_ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def _base_qs():
    return (
        TutoringRegistration.objects.select_related(
            "student", "instructor", "resource", "student_payback_account"
        ).prefetch_related(
            "submissions", "commission_invoices", "resource__files"
        )
    )


def _request_id(request) -> str:
    return request.headers.get("X-Request-ID", "")


class TutoringRegistrationListView(ListAPIView):
    """GET /admin-api/v1/tutoring-registrations/

    필터: ``contract_status``, ``attribute_validation_status``,
    ``fee_payment_status``, ``q``(학생/강사 실명·닉네임·이메일 검색), ``ordering``.
    기본 PageNumberPagination(20/page).
    """

    permission_classes = [IsSuperAdmin]
    serializer_class = TutoringRegistrationListSerializer

    def get_queryset(self):
        qs = _base_qs()
        params = self.request.query_params

        contract = params.get("contract_status")
        if contract in _CONTRACT_VALUES:
            qs = qs.filter(contract_status=contract)

        validation = params.get("attribute_validation_status")
        if validation in _VALIDATION_VALUES:
            qs = qs.filter(attribute_validation_status=validation)

        fee = params.get("fee_payment_status")
        if fee in _FEE_VALUES:
            qs = qs.filter(resource__fee_payment_status=fee)

        q = (params.get("q") or "").strip()
        if q:
            qs = qs.annotate(
                _student_full=Concat("student__last_name", "student__first_name"),
                _instructor_full=Concat(
                    "instructor__last_name", "instructor__first_name"
                ),
            ).filter(
                Q(_student_full__icontains=q)
                | Q(_instructor_full__icontains=q)
                | Q(student__user_name__icontains=q)
                | Q(student__username__icontains=q)
                | Q(student__email__icontains=q)
                | Q(instructor__user_name__icontains=q)
                | Q(instructor__username__icontains=q)
                | Q(instructor__email__icontains=q)
            )

        ordering = params.get("ordering", "-created_at")
        field = ordering.lstrip("-")
        if field not in _ORDERABLE_FIELDS:
            return qs.order_by("-created_at")

        if field == "commission_amount":
            # 수수료 금액은 연결 INITIAL 인보이스 값이므로 서브쿼리로 annotate 후 정렬한다.
            # 인보이스 없는 등록(NULL)은 항상 뒤로 보낸다.
            qs = qs.annotate(
                _commission_amount=Subquery(
                    CommissionInvoice.objects.filter(
                        registration=OuterRef("pk"),
                        invoice_type=CommissionInvoice.InvoiceType.INITIAL,
                    ).values("commission_amount")[:1]
                )
            )
            expr = F("_commission_amount")
            expr = expr.desc(nulls_last=True) if ordering.startswith("-") else expr.asc(nulls_last=True)
            return qs.order_by(expr)

        return qs.order_by(ordering)


class TutoringRegistrationSummaryView(APIView):
    """GET /admin-api/v1/tutoring-registrations/summary/

    계약 상태별 건수 + 수수료 확인 대기 건수(관리자 액션 필요 지표)를 반환합니다.
    예) {"COLLECTING": 2, "REGISTERED": 3, "ACTIVE": 5, "CANCELLED": 1,
         "total": 11, "awaiting_confirmation": 2}
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = TutoringRegistration.objects.values("contract_status").annotate(
            n=Count("id")
        )
        counts = {row["contract_status"]: row["n"] for row in rows}
        data = {value: counts.get(value, 0) for value in _CONTRACT_VALUES}
        data["total"] = sum(data.values())
        data["awaiting_confirmation"] = TutoringResource.objects.filter(
            fee_payment_status="AWAITING_CONFIRMATION",
            registration__isnull=False,
        ).count()
        return Response(data)


class TutoringRegistrationDetailView(RetrieveAPIView):
    """GET /admin-api/v1/tutoring-registrations/{pk}/"""

    permission_classes = [IsSuperAdmin]
    serializer_class = TutoringRegistrationDetailSerializer

    def get_queryset(self):
        return _base_qs()


class TutoringRegistrationConfirmFeeView(APIView):
    """POST /admin-api/v1/tutoring-registrations/{pk}/confirm-fee/

    수수료 입금 확인(AWAITING_CONFIRMATION → PAID). 입력 없음.
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        registration = get_object_or_404(TutoringRegistration, pk=pk)
        try:
            service.confirm_fee(
                registration,
                admin=request.user,
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        updated = _base_qs().get(pk=pk)
        return Response(TutoringRegistrationDetailSerializer(updated).data)


class TutoringRegistrationRejectFeeView(APIView):
    """POST /admin-api/v1/tutoring-registrations/{pk}/reject-fee/ (사유 선택)"""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = RejectFeeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration = get_object_or_404(TutoringRegistration, pk=pk)
        try:
            service.reject_fee(
                registration,
                admin=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        updated = _base_qs().get(pk=pk)
        return Response(TutoringRegistrationDetailSerializer(updated).data)


class TutoringRegistrationDocumentView(APIView):
    """GET /admin-api/v1/tutoring-registrations/{pk}/documents/{file_id}/

    슈퍼관리자만 접근 가능한 보호 스트리밍 엔드포인트입니다. raw 미디어 URL 을
    노출하지 않고, 해당 등록에 연결된 증빙 파일(pdf/jpg/png)만
    ``Content-Disposition: inline`` 으로 제공합니다. Next BFF(Token)와
    Django Admin(세션) 접근을 모두 허용합니다.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk, file_id):
        try:
            document = TutoringResourceFile.objects.get(
                pk=file_id, tutoring_resource__registration_id=pk
            )
        except TutoringResourceFile.DoesNotExist as exc:
            raise Http404("Document not found") from exc

        name = document.file.name
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in _ALLOWED_DOCUMENT_EXTENSIONS:
            raise Http404("Unsupported document type")

        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        try:
            file_handle = document.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Document file missing") from exc

        return FileResponse(
            file_handle,
            as_attachment=False,
            filename=os.path.basename(name),
            content_type=content_type,
        )
