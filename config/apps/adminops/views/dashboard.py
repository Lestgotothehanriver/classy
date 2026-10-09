"""관리자 운영 대시보드 조회 API입니다."""

from django.db.models import Count, Min, Sum
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.cash.models import SettlementRecord
from config.apps.pending.models import PendingInstructor
from config.apps.report.models import Report, ReportStatusChoices
from config.apps.tutoring.models import TutoringResource
from config.apps.support.models import SupportTicket

from ..permissions import IsSuperAdmin


def _display_name(*, first_name: str, last_name: str, user_name: str) -> str:
    """관리자 큐에서 사용할 사용자 표시 이름을 반환합니다."""
    return f"{first_name}{last_name}".strip() or user_name


def _registration_subtitle(resource: TutoringResource) -> str:
    """성사등록 수수료 큐에서 학생과 강사의 표시 이름을 조합합니다."""
    registration = resource.registration
    student = registration.student
    instructor = registration.instructor
    student_name = _display_name(
        first_name=student.first_name,
        last_name=student.last_name,
        user_name=student.user_name,
    )
    instructor_name = _display_name(
        first_name=instructor.first_name,
        last_name=instructor.last_name,
        user_name=instructor.user_name,
    )
    return f"{student_name} 학생 · {instructor_name} 강사"


class OperationsDashboardView(APIView):
    """GET /admin-api/v1/dashboard/operations/ - 운영 처리 대기 현황을 반환합니다.

    큐는 안전·금전 관련 업무를 우선해 신규 신고, 수수료 입금 확인, 정산 요청,
    학력 인증 신청 순으로 정렬합니다. 같은 업무에서는 오래 대기한 항목이 먼저 옵니다.
    """

    permission_classes = [IsSuperAdmin]
    queue_limit = 12

    def get(self, request):
        """현재 처리 대기 요약과 상세 화면으로 이동할 수 있는 큐를 반환합니다."""
        pending_reports = Report.objects.filter(status=ReportStatusChoices.PENDING)
        reports_in_review = Report.objects.filter(
            status=ReportStatusChoices.IN_REVIEW
        ).count()
        awaiting_fee = TutoringResource.objects.filter(
            fee_payment_status="AWAITING_CONFIRMATION",
            registration__isnull=False,
        )
        pending_settlements = SettlementRecord.objects.filter(status="PENDING")
        pending_verifications = PendingInstructor.objects.filter(
            status=PendingInstructor.Status.PENDING
        )
        support_tickets = SupportTicket.objects.exclude(status=SupportTicket.Status.CLOSED)

        summary = {
            "pending_reports": pending_reports.count(),
            "reports_in_review": reports_in_review,
            "awaiting_fee_confirmation": awaiting_fee.count(),
            "pending_settlements": pending_settlements.count(),
            "pending_settlement_amount": pending_settlements.aggregate(
                total=Coalesce(Sum("amount"), 0)
            )["total"],
            "pending_verifications": pending_verifications.count(),
            "support_received": support_tickets.filter(status=SupportTicket.Status.RECEIVED).count(),
            "support_unassigned": support_tickets.filter(assigned_to__isnull=True).count(),
            "support_in_progress": support_tickets.filter(status=SupportTicket.Status.IN_PROGRESS).count(),
            "support_waiting_for_user": support_tickets.filter(status=SupportTicket.Status.WAITING_FOR_USER).count(),
        }
        summary["action_required"] = sum(
            (
                summary["pending_reports"],
                summary["awaiting_fee_confirmation"],
                summary["pending_settlements"],
                summary["pending_verifications"],
                summary["support_received"],
            )
        )

        queue = self._report_items(pending_reports)
        queue.extend(self._fee_confirmation_items(awaiting_fee))
        queue.extend(self._settlement_items(pending_settlements))
        queue.extend(self._verification_items(pending_verifications))

        return Response({"summary": summary, "queue": queue[: self.queue_limit]})

    def _report_items(self, queryset):
        """신규 신고를 피신고 사용자 단위의 처리 큐 항목으로 묶습니다."""
        rows = (
            queryset.values(
                "reported_user_id",
                "reported_user__first_name",
                "reported_user__last_name",
                "reported_user__user_name",
            )
            .annotate(report_count=Count("id"), queued_at=Min("created_at"))
            .order_by("queued_at", "reported_user_id")[: self.queue_limit]
        )
        return [
            {
                "kind": "report",
                "target_id": row["reported_user_id"],
                "title": _display_name(
                    first_name=row["reported_user__first_name"],
                    last_name=row["reported_user__last_name"],
                    user_name=row["reported_user__user_name"],
                ),
                "subtitle": f"신규 신고 {row['report_count']}건",
                "queued_at": row["queued_at"],
            }
            for row in rows
        ]

    def _fee_confirmation_items(self, queryset):
        """수수료 입금 확인 대기 성사등록 항목을 반환합니다."""
        rows = queryset.select_related(
            "registration__student", "registration__instructor"
        ).order_by("registration__updated_at", "registration_id")[: self.queue_limit]
        return [
            {
                "kind": "fee_confirmation",
                "target_id": resource.registration_id,
                "title": resource.registration.subject,
                "subtitle": _registration_subtitle(resource),
                "queued_at": resource.registration.updated_at,
            }
            for resource in rows
        ]

    def _settlement_items(self, queryset):
        """정산 요청 대기 항목을 반환합니다."""
        rows = queryset.select_related("instructor__user").order_by("created_at", "pk")[
            : self.queue_limit
        ]
        return [
            {
                "kind": "settlement",
                "target_id": settlement.pk,
                "title": _display_name(
                    first_name=settlement.instructor.user.first_name,
                    last_name=settlement.instructor.user.last_name,
                    user_name=settlement.instructor.user.user_name,
                ),
                "subtitle": f"정산 요청 {settlement.amount:,}C",
                "queued_at": settlement.created_at,
            }
            for settlement in rows
        ]

    def _verification_items(self, queryset):
        """학력 인증 대기 항목을 반환합니다."""
        rows = queryset.select_related("instructor_profile__user").order_by(
            "applied_at", "pk"
        )[: self.queue_limit]
        return [
            {
                "kind": "verification",
                "target_id": pending.pk,
                "title": _display_name(
                    first_name=pending.instructor_profile.user.first_name,
                    last_name=pending.instructor_profile.user.last_name,
                    user_name=pending.instructor_profile.user.user_name,
                ),
                "subtitle": pending.instructor_profile.university or "학력 인증 신청",
                "queued_at": pending.applied_at,
            }
            for pending in rows
        ]
