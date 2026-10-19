from django.db.models import (
    Avg,
    BooleanField,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    FloatField,
    OuterRef,
    Q,
    Value,
)
from config.apps.accounts.models import Student, InstructorLike

class InstructorAnnotateMixin:
    """강사 QuerySet에 평점·리뷰 수·좋아요 수를 annotate합니다."""
    
    def annotate_instructor_stats(self, qs, request_user=None):
        student = None
        if request_user and request_user.is_authenticated:
            student = Student.objects.filter(user=request_user).first()

        if student:
            qs = qs.annotate(
                is_liked=Exists(
                    InstructorLike.objects.filter(
                        student=student,
                        instructor=OuterRef("pk")
                    )
                )
            )
        else:
            qs = qs.annotate(is_liked=Value(False, output_field=BooleanField()))

        qs = qs.annotate(
            average_rate=Avg(
                ExpressionWrapper(
                    (F("instructor_reviews__professionalism") +
                     F("instructor_reviews__teaching_skill") +
                     F("instructor_reviews__punctuality")) / 3.0,
                    output_field=FloatField()
                )
            ),
            review_count=Count("instructor_reviews", distinct=True),
            like_count=Count("liked_by", distinct=True),
            # 수수료 납부 완료 및 활성 계약이 모두 확인된 과외만 집계한다.
            tutoring_count=Count(
                "tutoring_resources",
                filter=Q(
                    tutoring_resources__fee_payment_status="PAID",
                    tutoring_resources__registration__contract_status="ACTIVE",
                ),
                distinct=True,
            ),
            average_cost=Avg(
                "tutoring_resources__first_month_fee",
                filter=Q(
                    tutoring_resources__fee_payment_status="PAID",
                    tutoring_resources__registration__contract_status="ACTIVE",
                ),
            ),
        )
        return qs
