"""정산(Settlement) 관리 API 뷰입니다.

학력 인증(instructor_verification) 뷰와 동일한 패턴을 따릅니다. 모두 슈퍼관리자
전용이며, 상태 전이(완료/취소)는 서비스 계층에 위임하고 ``AdminOpsError`` 를
``{"error": ...}`` 응답으로 변환합니다.
"""

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, Concat
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.cash.models import SettlementRecord

from ..exceptions import AdminOpsError
from ..permissions import IsSuperAdmin
from ..serializers import (
    SettlementCancelSerializer,
    SettlementCompleteSerializer,
    SettlementDetailSerializer,
    SettlementListSerializer,
)
from ..services import settlement as service

_STATUS_VALUES = {value for value, _ in SettlementRecord.STATUS_CHOICES}
_ORDERABLE_FIELDS = {"created_at", "processed_at", "amount", "status"}


def _base_qs():
    return (
        SettlementRecord.objects.select_related("instructor__user")
        .annotate(rental_count=Count("rentals"))
    )


def _request_id(request) -> str:
    return request.headers.get("X-Request-ID", "")


class SettlementListView(ListAPIView):
    """GET /admin-api/v1/settlements/

    필터: ``status``, ``q``(강사 실명/닉네임/이메일 검색), ``ordering``.
    기본 PageNumberPagination(20/page).
    """

    permission_classes = [IsSuperAdmin]
    serializer_class = SettlementListSerializer

    def get_queryset(self):
        qs = _base_qs()
        params = self.request.query_params

        status_filter = params.get("status")
        if status_filter in _STATUS_VALUES:
            qs = qs.filter(status=status_filter)

        q = (params.get("q") or "").strip()
        if q:
            qs = qs.annotate(
                _full_name=Concat(
                    "instructor__user__last_name",
                    "instructor__user__first_name",
                )
            ).filter(
                Q(_full_name__icontains=q)
                | Q(instructor__user__first_name__icontains=q)
                | Q(instructor__user__last_name__icontains=q)
                | Q(instructor__user__user_name__icontains=q)
                | Q(instructor__user__email__icontains=q)
            )

        ordering = params.get("ordering", "-created_at")
        if ordering.lstrip("-") in _ORDERABLE_FIELDS:
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by("-created_at")
        return qs


class SettlementSummaryView(APIView):
    """GET /admin-api/v1/settlements/summary/

    상태별 건수와 대기 금액 합계를 반환합니다.
    예) {"PENDING": 3, "COMPLETED": 1, "CANCELED": 0, "total": 4, "pending_amount": 120000}
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = SettlementRecord.objects.values("status").annotate(n=Count("id"))
        counts = {row["status"]: row["n"] for row in rows}
        data = {value: counts.get(value, 0) for value in _STATUS_VALUES}
        data["total"] = sum(data.values())
        data["pending_amount"] = SettlementRecord.objects.filter(
            status="PENDING"
        ).aggregate(total=Coalesce(Sum("amount"), 0))["total"]
        return Response(data)


class SettlementDetailView(RetrieveAPIView):
    """GET /admin-api/v1/settlements/{pk}/"""

    permission_classes = [IsSuperAdmin]
    serializer_class = SettlementDetailSerializer

    def get_queryset(self):
        return _base_qs()


class SettlementCompleteView(APIView):
    """POST /admin-api/v1/settlements/{pk}/complete/ (지급 참조번호 필수)"""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = SettlementCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        settlement = get_object_or_404(SettlementRecord, pk=pk)
        try:
            service.complete(
                settlement,
                admin=request.user,
                payment_reference=serializer.validated_data["payment_reference"],
                admin_note=serializer.validated_data.get("admin_note", ""),
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        updated = _base_qs().get(pk=pk)
        return Response(SettlementDetailSerializer(updated).data)


class SettlementCancelView(APIView):
    """POST /admin-api/v1/settlements/{pk}/cancel/ (연결 대여 롤백)"""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = SettlementCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        settlement = get_object_or_404(SettlementRecord, pk=pk)
        try:
            service.cancel(
                settlement,
                admin=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request_id=_request_id(request),
            )
        except AdminOpsError as exc:
            return Response({"error": exc.message}, status=exc.default_status)
        updated = _base_qs().get(pk=pk)
        return Response(SettlementDetailSerializer(updated).data)
