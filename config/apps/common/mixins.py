from django.db.models import Avg, Count, F, ExpressionWrapper, FloatField, OuterRef, Subquery, Value, BooleanField, Exists
from django.db.models import IntegerField as DjangoIntField
from config.apps.accounts.models import Student, InstructorLike
from config.apps.cash.models import InstructorMonthlyRank

class InstructorAnnotateMixin:
    """강사 QuerySet에 평점/리뷰수/좋아요수/랭킹을 annotate합니다."""
    
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

        latest_rank_qs = InstructorMonthlyRank.objects.filter(
            instructor=OuterRef("pk")
        ).order_by("-year", "-month").values("rank")[:1]

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
            current_rank=Subquery(latest_rank_qs, output_field=DjangoIntField()),
        )
        return qs
