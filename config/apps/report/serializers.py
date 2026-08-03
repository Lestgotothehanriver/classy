from django.db import transaction
from rest_framework import serializers

from .models import (
    Report,
    ReportChoice,
    ReportReasonChoices,
    ReportSourceChoices,
)


class ReportReasonField(serializers.ChoiceField):
    """현재 코드와 이전 앱에서 사용한 신고 사유 코드를 모두 허용한다."""

    aliases = {
        "INAPPROPRIATE_CONTENT": ReportReasonChoices.INAPPROPRIATE_CONTENT,
        "FALSE_INFORMATION": ReportReasonChoices.FALSE_INFORMATION,
        "PROFANITY": ReportReasonChoices.ABUSIVE_LANGUAGE,
        "ABUSIVE_LANGUAGE": ReportReasonChoices.ABUSIVE_LANGUAGE,
        "UNREASONABLE_DEMAND": ReportReasonChoices.EXCESSIVE_REQUEST,
        "EXCESSIVE_REQUEST": ReportReasonChoices.EXCESSIVE_REQUEST,
        "UNREPORTED_CLASS": ReportReasonChoices.UNREPORTED_CLASS_COMPLETION,
        "UNREPORTED_CLASS_COMPLETION": ReportReasonChoices.UNREPORTED_CLASS_COMPLETION,
        "OTHER": ReportReasonChoices.OTHER,
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = self.aliases.get(data, data.lower())
        return super().to_internal_value(data)


class ReportCreateSerializer(serializers.Serializer):
    """
    신고 생성 Serializer.

    앱은 신고 맥락 ``source`` 와 대상 id ``target_id`` 를 보낸다. 콘텐츠·프로필·채팅
    신고의 책임 주체(``reported_user``)는 **서버가 대상 소유자로 도출**하므로
    클라이언트가 보낸 ``reported_user`` 는 신뢰하지 않는다. 구(舊) 앱 호환을 위해
    ``source`` 가 없으면 종전처럼 ``reported_user`` 를 사용한다.

    Request body(신):
    {
        "source": "lecture",           # teacher_profile|chat|lecture|comment|tutoring_post
        "target_id": 12,               # 대상 콘텐츠/프로필/채팅방 id
        "description": "부적절합니다",
        "evidence_image": null,
        "choices": ["inappropriate_content", "abusive_language"]
    }
    """
    reported_user = serializers.IntegerField(
        required=False, help_text="구 앱 호환용(서버 도출 시 무시)"
    )
    source = serializers.CharField(required=False, help_text="신고 맥락")
    target_id = serializers.IntegerField(
        required=False, help_text="대상 콘텐츠/프로필/채팅방 id"
    )
    description = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="자유서술"
    )
    evidence_image = serializers.ImageField(required=False, allow_null=True)
    choices = serializers.ListField(
        child=ReportReasonField(choices=ReportReasonChoices.choices),
        min_length=1,
        help_text="신고 사유 목록 (최소 1개)",
    )

    _VALID_SOURCES = set(ReportSourceChoices.values)

    # ------------------------------------------------------------------
    # Validation & 소유자 도출
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_400(model, pk):
        try:
            return model.objects.get(pk=pk)
        except model.DoesNotExist:
            raise serializers.ValidationError(
                {"target_id": "신고 대상을 찾을 수 없습니다."}
            )

    def _resolve(self, source, target_id, reporter):
        """(content_object|None, reported_user) 도출. 채팅은 content_object 미저장."""
        if not target_id:
            raise serializers.ValidationError(
                {"target_id": "신고 대상 id가 필요합니다."}
            )
        S = ReportSourceChoices
        if source == S.LECTURE:
            from config.apps.lecture.models import Lecture
            obj = self._get_or_400(Lecture, target_id)
            return obj, obj.instructor.user
        if source == S.COMMENT:
            from config.apps.lecture.models import Comment
            obj = self._get_or_400(Comment, target_id)
            return obj, obj.author
        if source == S.TUTORING_POST:
            from config.apps.tutoring.models import TutoringPost
            obj = self._get_or_400(TutoringPost, target_id)
            return obj, obj.student.user
        if source == S.TEACHER_PROFILE:
            from config.apps.accounts.models import Instructor
            obj = self._get_or_400(Instructor, target_id)
            return obj, obj.user
        if source == S.CHAT:
            # 개인정보 보호: 채팅은 content_object 를 저장하지 않고 상대만 도출한다.
            from config.apps.chat_app.models import ChatRoom
            room = self._get_or_400(ChatRoom, target_id)
            instructor_user = room.instructor.user
            student_user = room.student.user
            reported = (
                student_user
                if reporter and reporter.pk == instructor_user.pk
                else instructor_user
            )
            return None, reported
        raise serializers.ValidationError({"source": "지원하지 않는 맥락입니다."})

    def validate(self, attrs):
        request = self.context.get("request")
        reporter = request.user if request else None

        source = (attrs.get("source") or "").lower()
        if source:
            if source not in self._VALID_SOURCES:
                raise serializers.ValidationError(
                    {"source": "알 수 없는 신고 맥락입니다."}
                )
            attrs["source"] = source
            content_object, reported_user = self._resolve(
                source, attrs.get("target_id"), reporter
            )
        else:
            # 구 앱 호환: source 미전송 시 reported_user 를 그대로 사용.
            rid = attrs.get("reported_user")
            if not rid:
                raise serializers.ValidationError(
                    {"reported_user": "신고 대상이 필요합니다."}
                )
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                reported_user = User.objects.get(pk=rid)
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"reported_user": "해당 사용자가 존재하지 않습니다."}
                )
            content_object = None

        if reporter and reported_user.pk == reporter.pk:
            raise serializers.ValidationError(
                {"reported_user": "자기 자신을 신고할 수 없습니다."}
            )

        attrs["_content_object"] = content_object
        attrs["_reported_user"] = reported_user
        return attrs

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, validated_data):
        reporter = self.context["request"].user
        reported_user = validated_data["_reported_user"]
        content_object = validated_data.get("_content_object")
        choices_data = validated_data["choices"]
        # source 미전송(구 앱)은 모델 기본값을 따른다.
        source = validated_data.get("source")

        with transaction.atomic():
            report = Report(
                reporter=reporter,
                reported_user=reported_user,
                description=validated_data.get("description", ""),
                evidence_image=validated_data.get("evidence_image"),
            )
            if source:
                report.source = source
            if content_object is not None:
                report.content_object = content_object
            report.save()

            ReportChoice.objects.bulk_create([
                ReportChoice(report=report, content=choice)
                for choice in choices_data
            ])

        return report


class ReportResponseSerializer(serializers.ModelSerializer):
    """신고 생성 응답용 Serializer."""
    choices = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "reporter",
            "reported_user",
            "source",
            "description",
            "status",
            "evidence_image",
            "choices",
            "created_at",
        ]
        read_only_fields = fields

    def get_choices(self, obj):
        return list(obj.choices.values_list("content", flat=True))


class InquirySerializer(serializers.ModelSerializer):
    """1:1 문의 Serializer."""
    class Meta:
        from .models import Inquiry
        model = Inquiry
        fields = ['id', 'user', 'title', 'content', 'is_resolved', 'created_at']
        read_only_fields = ['id', 'user', 'is_resolved', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)
