from django.db import transaction
from rest_framework import serializers

from .models import Report, ReportChoice, ReportReasonChoices


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

    Request body:
    {
        "reported_user": 3,
        "evidence_image": null,
        "choices": ["inappropriate_content", "abusive_language", "other"]
    }
    """
    reported_user = serializers.IntegerField(help_text="신고할 대상 사용자 ID")
    evidence_image = serializers.ImageField(required=False, allow_null=True)
    choices = serializers.ListField(
        child=ReportReasonField(choices=ReportReasonChoices.choices),
        min_length=1,
        help_text="신고 사유 목록 (최소 1개)",
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_reported_user(self, value):
        """reported_user가 존재하는지 확인."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("해당 사용자가 존재하지 않습니다.")
        return value

    def validate(self, attrs):
        """reporter와 reported_user가 동일 사용자가 아닌지 확인."""
        request = self.context.get("request")
        if request and request.user.pk == attrs["reported_user"]:
            raise serializers.ValidationError(
                {"reported_user": "자기 자신을 신고할 수 없습니다."}
            )
        return attrs

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, validated_data):
        choices_data = validated_data.pop("choices")
        reporter = self.context["request"].user

        with transaction.atomic():
            report = Report.objects.create(
                reporter=reporter,
                reported_user_id=validated_data["reported_user"],
                evidence_image=validated_data.get("evidence_image"),
            )

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
