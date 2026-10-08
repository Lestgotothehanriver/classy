from io import BytesIO

from django.core.files.images import get_image_dimensions
from django.utils import timezone
from PIL import Image
from rest_framework import serializers

from config.apps.common.serializers import AbsoluteImageField
from config.apps.notice.models import Notice


_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_BANNER_SIZE_BYTES = 5 * 1024 * 1024
_BANNER_ASPECT_RATIO = 3.0
_BANNER_RATIO_TOLERANCE = 0.1


class AdminNoticeSerializer(serializers.ModelSerializer):
    """관리자 공지 작성·수정 및 목록·상세 응답 serializer 입니다."""

    banner_image = AbsoluteImageField(required=False, allow_null=True)
    remove_banner_image = serializers.BooleanField(write_only=True, required=False, default=False)
    effective_status = serializers.CharField(read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    updated_by_email = serializers.EmailField(source="updated_by.email", read_only=True)

    class Meta:
        model = Notice
        fields = [
            "id",
            "title",
            "summary",
            "content",
            "banner_image",
            "remove_banner_image",
            "status",
            "effective_status",
            "publish_at",
            "exposure_type",
            "exposure_ends_at",
            "banner_order",
            "created_by_email",
            "updated_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "effective_status",
            "created_by_email",
            "updated_by_email",
            "created_at",
            "updated_at",
        ]

    def validate_banner_image(self, image):
        """홈 배너 이미지의 형식·용량·3:1 비율을 검증합니다."""
        if image is None:
            return image
        if getattr(image, "content_type", "") not in _ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError("JPG, PNG, WebP 이미지만 업로드할 수 있습니다.")
        if image.size > _MAX_BANNER_SIZE_BYTES:
            raise serializers.ValidationError("배너 이미지는 5MB 이하여야 합니다.")
        try:
            raw = image.read()
            with Image.open(BytesIO(raw)) as opened:
                width, height = opened.size
                opened.verify()
            image.seek(0)
        except Exception as error:
            raise serializers.ValidationError("유효한 이미지 파일이 아닙니다.") from error
        if not width or not height:
            raise serializers.ValidationError("배너 이미지 크기를 확인할 수 없습니다.")
        ratio = width / height
        if abs(ratio - _BANNER_ASPECT_RATIO) > _BANNER_RATIO_TOLERANCE:
            raise serializers.ValidationError("배너 이미지는 3:1 비율이어야 합니다.")
        return image

    def validate(self, attrs):
        """게시·홈 노출 규칙과 예약 시간 충돌을 검증합니다."""
        instance = self.instance
        status = attrs.get("status", getattr(instance, "status", Notice.PublicationStatus.DRAFT))
        exposure_type = attrs.get(
            "exposure_type", getattr(instance, "exposure_type", Notice.ExposureType.LIST)
        )
        publish_at = attrs.get("publish_at", getattr(instance, "publish_at", None))
        exposure_ends_at = attrs.get(
            "exposure_ends_at", getattr(instance, "exposure_ends_at", None)
        )
        banner_order = attrs.get("banner_order", getattr(instance, "banner_order", None))
        remove_image = attrs.get("remove_banner_image", False)
        uploaded_image = attrs.get("banner_image", serializers.empty)
        current_image = getattr(instance, "banner_image", None)
        has_image = bool(current_image) and not remove_image
        if uploaded_image is not serializers.empty:
            has_image = uploaded_image is not None

        if remove_image and uploaded_image is not serializers.empty and uploaded_image is not None:
            raise serializers.ValidationError({"banner_image": "이미지를 교체하거나 삭제 중 하나만 선택해주세요."})
        if status == Notice.PublicationStatus.PUBLISHED and publish_at is None:
            raise serializers.ValidationError({"publish_at": "게시 시각을 입력해주세요."})
        if exposure_type == Notice.ExposureType.LIST:
            if exposure_ends_at is not None or banner_order is not None:
                raise serializers.ValidationError("목록 공지는 노출 종료 시각과 배너 순서를 설정할 수 없습니다.")
        elif status == Notice.PublicationStatus.PUBLISHED:
            if exposure_ends_at is None:
                raise serializers.ValidationError({"exposure_ends_at": "노출 종료 시각을 입력해주세요."})
            if exposure_ends_at <= publish_at:
                raise serializers.ValidationError({"exposure_ends_at": "노출 종료 시각은 게시 시각보다 늦어야 합니다."})
            if exposure_type == Notice.ExposureType.HOME_BANNER:
                if not has_image:
                    raise serializers.ValidationError({"banner_image": "홈 배너에는 이미지가 필요합니다."})
                if banner_order is None or not 1 <= banner_order <= 3:
                    raise serializers.ValidationError({"banner_order": "배너 순서는 1~3 중 하나여야 합니다."})
            elif banner_order is not None:
                raise serializers.ValidationError({"banner_order": "긴급 모달에는 배너 순서를 설정할 수 없습니다."})

            overlaps = Notice.objects.filter(
                status=Notice.PublicationStatus.PUBLISHED,
                exposure_type=exposure_type,
                publish_at__lt=exposure_ends_at,
                exposure_ends_at__gt=publish_at,
            )
            if instance:
                overlaps = overlaps.exclude(pk=instance.pk)
            if exposure_type == Notice.ExposureType.HOME_BANNER and overlaps.count() >= 3:
                raise serializers.ValidationError("같은 기간에 노출할 홈 배너는 최대 3개입니다.")
            if exposure_type == Notice.ExposureType.EMERGENCY_MODAL and overlaps.exists():
                raise serializers.ValidationError("같은 기간에 노출할 긴급 모달은 하나만 설정할 수 있습니다.")
        return attrs

    def update(self, instance, validated_data):
        remove_image = validated_data.pop("remove_banner_image", False)
        old_image = instance.banner_image if instance.banner_image else None
        image_is_replaced = "banner_image" in validated_data
        if remove_image:
            validated_data["banner_image"] = None
        updated = super().update(instance, validated_data)
        if old_image and (remove_image or image_is_replaced):
            old_image.delete(save=False)
        return updated

    def create(self, validated_data):
        """모델 필드가 아닌 이미지 삭제 플래그를 제외하고 공지를 생성합니다."""
        validated_data.pop("remove_banner_image", None)
        return super().create(validated_data)
