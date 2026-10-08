from rest_framework import serializers

from config.apps.common.serializers import AbsoluteImageField

from .models import Notice


class NoticeListSerializer(serializers.ModelSerializer):
    """사용자용 공지 목록 응답입니다."""

    banner_image = AbsoluteImageField(read_only=True)

    class Meta:
        model = Notice
        fields = [
            "id",
            "title",
            "summary",
            "banner_image",
            "publish_at",
            "exposure_type",
        ]


class NoticeDetailSerializer(NoticeListSerializer):
    """사용자용 공지 상세 응답입니다."""

    class Meta(NoticeListSerializer.Meta):
        fields = NoticeListSerializer.Meta.fields + ["content", "updated_at"]


class NoticeExposureSerializer(NoticeListSerializer):
    """홈 배너와 앱 공지 모달에 필요한 공지 응답입니다."""

    class Meta(NoticeListSerializer.Meta):
        fields = NoticeListSerializer.Meta.fields + ["exposure_ends_at", "banner_order"]
