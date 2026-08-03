"""신고 관리(adminops) 직렬화기입니다.

가해자(reported_user) 중심 큐/케이스를 직렬화한다. 큐 목록은 User 인스턴스에 집계
annotate 를 얹어 사용하고(``ReportedUserListSerializer``), 케이스 상세는 그 유저의
신고를 ``source`` 별로 묶어 개별 신고·제재 이력·처리 추천을 제공한다
(``ReportCaseSerializer``). 콘텐츠 열람(영상 스트리밍/댓글 원문 등)은 Phase 2에서
``content_object`` 직렬화로 확장한다.
"""

from rest_framework import serializers

from config.apps.accounts.models import UserSanction
from config.apps.report.models import ReportStatusChoices

from .instructor_verification import _real_name


def _reasons(report):
    return list(report.choices.values_list("content", flat=True))


def _recommend_sanction(effective_count: int, prior_types: set) -> str | None:
    """유효 신고수 + 과거 제재 유형으로 다음 제재 수위를 추천한다.

    유효 신고수는 RESOLVED(조치완료)만 집계하므로 무혐의(DISMISSED)로 반복 신고당한
    유저를 과대평가하지 않는다.
    """
    T = UserSanction.Type
    if T.PERMANENT_BAN in prior_types:
        return None  # 이미 영구정지
    if T.SUSPENSION in prior_types:
        return T.PERMANENT_BAN
    if T.WARNING in prior_types or effective_count >= 3:
        return T.SUSPENSION
    return T.WARNING


class ReportedUserListSerializer(serializers.Serializer):
    """피신고 유저 큐 항목(집계 annotate 가 얹힌 User 인스턴스를 직렬화)."""

    user_id = serializers.IntegerField(source="pk")
    real_name = serializers.SerializerMethodField()
    user_name = serializers.CharField()
    email = serializers.EmailField()
    is_banned = serializers.BooleanField()
    pending_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
    effective_count = serializers.IntegerField()
    unique_reporters = serializers.IntegerField()
    active_sanction_count = serializers.IntegerField()
    last_reported_at = serializers.DateTimeField()
    risk_score = serializers.SerializerMethodField()

    def get_real_name(self, obj) -> str:
        return _real_name(obj)

    def get_risk_score(self, obj) -> int:
        effective = getattr(obj, "effective_count", 0) or 0
        pending = getattr(obj, "pending_count", 0) or 0
        reporters = getattr(obj, "unique_reporters", 0) or 0
        return effective * 3 + pending + reporters * 2


class ReportItemSerializer(serializers.ModelSerializer):
    """케이스 상세의 개별 신고 한 건."""

    reporter_name = serializers.SerializerMethodField()
    reasons = serializers.SerializerMethodField()
    has_evidence = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()

    class Meta:
        from config.apps.report.models import Report

        model = Report
        fields = [
            "id",
            "source",
            "status",
            "description",
            "reasons",
            "has_evidence",
            "reporter_id",
            "reporter_name",
            "object_id",
            "content",
            "created_at",
        ]

    def get_reporter_name(self, obj) -> str:
        return _real_name(obj.reporter) if obj.reporter_id else ""

    def get_reasons(self, obj) -> list:
        return _reasons(obj)

    def get_has_evidence(self, obj) -> bool:
        return bool(obj.evidence_image)

    def get_content(self, obj):
        """source 별 열람 대상(content_object)을 어드민 표시용으로 직렬화한다.

        채팅은 개인정보 보호로 content_object 를 저장하지 않아 항상 None. 영상은
        메타만 반환하고 재생은 별도 보호 스트리밍(review-stream)으로 처리한다.
        """
        target = obj.content_object
        if target is None:
            return None
        source = obj.source
        if source == "lecture":
            return {
                "type": "lecture",
                "id": target.id,
                "title": target.title,
                "is_blocked": target.admin_blocked_at is not None,
            }
        if source == "comment":
            return {
                "type": "comment",
                "id": target.id,
                "text": target.content,
                "lecture_id": target.lecture_id,
                "lecture_title": getattr(target.lecture, "title", ""),
                "is_blocked": target.is_blocked,
            }
        if source == "tutoring_post":
            return {
                "type": "tutoring_post",
                "id": target.id,
                "title": target.title,
                "cost": target.cost,
                "situation": target.situation,
                "is_active": target.is_active,
                "is_blocked": target.admin_blocked_at is not None,
            }
        if source == "teacher_profile":
            return {
                "type": "teacher_profile",
                "id": target.id,
                "university": getattr(target, "university", ""),
                "department": getattr(target, "department", ""),
                "instruction": getattr(target, "instruction", ""),
            }
        return None


class SanctionItemSerializer(serializers.ModelSerializer):
    """제재 이력 한 건."""

    is_effective = serializers.BooleanField(read_only=True)
    issued_by_email = serializers.SerializerMethodField()

    class Meta:
        model = UserSanction
        fields = [
            "id",
            "type",
            "reason",
            "report_id",
            "starts_at",
            "expires_at",
            "is_active",
            "is_effective",
            "issued_by_email",
            "created_at",
        ]

    def get_issued_by_email(self, obj) -> str:
        return getattr(obj.issued_by, "email", "") if obj.issued_by_id else ""


class ReportCaseSerializer(serializers.Serializer):
    """가해자(User) 1명의 통합 케이스 상세."""

    def to_representation(self, user):
        reports = list(
            user.reports_received.select_related("reporter")
            .prefetch_related("choices")
            .order_by("-created_at")
        )
        sanctions = list(
            user.sanctions.select_related("issued_by").order_by("-created_at")
        )

        pending = [r for r in reports if r.status in
                   (ReportStatusChoices.PENDING, ReportStatusChoices.IN_REVIEW)]
        effective_count = sum(
            1 for r in reports if r.status == ReportStatusChoices.RESOLVED
        )
        unique_reporters = len({r.reporter_id for r in reports})

        # source 별 그룹핑(각 신고는 자기 맥락을 유지한다).
        groups: dict = {}
        for r in reports:
            groups.setdefault(r.source, []).append(r)
        reports_by_source = [
            {
                "source": src,
                "count": len(items),
                "reports": ReportItemSerializer(items, many=True).data,
            }
            for src, items in groups.items()
        ]

        return {
            "user_id": user.pk,
            "real_name": _real_name(user),
            "user_name": user.user_name,
            "email": user.email,
            "is_banned": user.is_banned,
            "counts": {
                "pending": len(pending),
                "total": len(reports),
                "effective": effective_count,
                "unique_reporters": unique_reporters,
                "sanction_history": len(sanctions),
            },
            "recommended_sanction": _recommend_sanction(
                effective_count, {s.type for s in sanctions}
            ),
            "reports_by_source": reports_by_source,
            "sanctions": SanctionItemSerializer(sanctions, many=True).data,
        }


class SanctionInputSerializer(serializers.Serializer):
    """제재 발급 입력. 기간 정지는 만료일이 필수, 경고·영구정지는 만료일 없음."""

    type = serializers.ChoiceField(choices=UserSanction.Type.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["type"] == UserSanction.Type.SUSPENSION and not attrs.get("expires_at"):
            raise serializers.ValidationError(
                {"expires_at": "기간 정지는 만료일이 필요합니다."}
            )
        if attrs["type"] in (UserSanction.Type.WARNING, UserSanction.Type.PERMANENT_BAN):
            attrs["expires_at"] = None
        return attrs


class ContentActionSerializer(serializers.Serializer):
    """콘텐츠 조치 한 건(영상 내리기/댓글 삭제 등)."""

    content_type = serializers.ChoiceField(
        choices=["lecture", "comment", "tutoring_post"]
    )
    object_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=["block", "unblock"], default="block")


class ResolveCaseSerializer(serializers.Serializer):
    """케이스 처리 입력: 종결 결과 + (선택) 콘텐츠 조치 + (선택) 제재."""

    outcome = serializers.ChoiceField(
        choices=[
            (ReportStatusChoices.RESOLVED, "조치완료"),
            (ReportStatusChoices.DISMISSED, "무혐의"),
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    sanction = SanctionInputSerializer(required=False, allow_null=True)
    content_actions = ContentActionSerializer(many=True, required=False, default=list)


class ContentBlockSerializer(serializers.Serializer):
    """단독 콘텐츠 차단/해제 입력."""

    content_type = serializers.ChoiceField(
        choices=["lecture", "comment", "tutoring_post"]
    )
    object_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=["block", "unblock"], default="block")
