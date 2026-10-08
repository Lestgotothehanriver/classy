from io import BytesIO

from PIL import Image
from rest_framework import serializers

from config.apps.common.serializers import AbsoluteImageField
from config.apps.notice.models import Notice


_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
_HOME_BANNER_ASPECT_RATIO = 3.0
_MOBILE_IMAGE_ASPECT_RATIO = 16 / 9
_ASPECT_RATIO_TOLERANCE = 0.1


class AdminNoticeSerializer(serializers.ModelSerializer):
    """관리자 공지 작성·수정 및 목록·상세 응답 serializer 입니다."""

    home_banner_image = AbsoluteImageField(required=False, allow_null=True)
    mobile_image = AbsoluteImageField(required=False, allow_null=True)
    remove_home_banner_image = serializers.BooleanField(
        write_only=True, required=False, default=False
    )
    remove_mobile_image = serializers.BooleanField(
        write_only=True, required=False, default=False
    )
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
            "home_banner_image",
            "mobile_image",
            "remove_home_banner_image",
            "remove_mobile_image",
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

    def _validate_image(self, image, *, label, aspect_ratio):
        """[image]의 공통 파일 제약과 [aspect_ratio]를 검증합니다."""
        if image is None:
            return image
        if getattr(image, "content_type", "") not in _ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError("JPG, PNG, WebP 이미지만 업로드할 수 있습니다.")
        if image.size > _MAX_IMAGE_SIZE_BYTES:
            raise serializers.ValidationError("이미지는 5MB 이하여야 합니다.")
        try:
            raw = image.read()
            with Image.open(BytesIO(raw)) as opened:
                width, height = opened.size
                opened.verify()
            image.seek(0)
        except Exception as error:
            raise serializers.ValidationError("유효한 이미지 파일이 아닙니다.") from error
        if not width or not height:
            raise serializers.ValidationError("이미지 크기를 확인할 수 없습니다.")
        if abs((width / height) - aspect_ratio) > _ASPECT_RATIO_TOLERANCE:
            raise serializers.ValidationError(
                f"{label}는 {aspect_ratio:g}:1 비율이어야 합니다."
            )
        return image

    def validate_home_banner_image(self, image):
        """웹 홈 배너 이미지의 형식·용량·3:1 비율을 검증합니다."""
        return self._validate_image(
            image,
            label="웹 홈 배너 이미지",
            aspect_ratio=_HOME_BANNER_ASPECT_RATIO,
        )

    def validate_mobile_image(self, image):
        """앱 공지 이미지의 형식·용량·16:9 비율을 검증합니다."""
        return self._validate_image(
            image,
            label="앱 공지 이미지",
            aspect_ratio=_MOBILE_IMAGE_ASPECT_RATIO,
        )

    @staticmethod
    def _has_image(current_image, uploaded_image, remove_image):
        """현재 이미지와 요청 값을 합쳐 최종 이미지 존재 여부를 반환합니다."""
        if uploaded_image is not serializers.empty:
            return uploaded_image is not None
        return bool(current_image) and not remove_image

    def validate(self, attrs):
        """게시·홈 노출 규칙과 두 이미지의 삭제·교체 충돌을 검증합니다."""
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
        remove_home_image = attrs.get("remove_home_banner_image", False)
        remove_mobile_image = attrs.get("remove_mobile_image", False)
        uploaded_home_image = attrs.get("home_banner_image", serializers.empty)
        uploaded_mobile_image = attrs.get("mobile_image", serializers.empty)
        has_home_image = self._has_image(
            getattr(instance, "home_banner_image", None),
            uploaded_home_image,
            remove_home_image,
        )
        has_mobile_image = self._has_image(
            getattr(instance, "mobile_image", None),
            uploaded_mobile_image,
            remove_mobile_image,
        )

        if remove_home_image and uploaded_home_image is not serializers.empty and uploaded_home_image is not None:
            raise serializers.ValidationError(
                {"home_banner_image": "이미지를 교체하거나 삭제 중 하나만 선택해주세요."}
            )
        if remove_mobile_image and uploaded_mobile_image is not serializers.empty and uploaded_mobile_image is not None:
            raise serializers.ValidationError(
                {"mobile_image": "이미지를 교체하거나 삭제 중 하나만 선택해주세요."}
            )
        if status == Notice.PublicationStatus.PUBLISHED and publish_at is None:
            raise serializers.ValidationError({"publish_at": "게시 시각을 입력해주세요."})
        if exposure_type == Notice.ExposureType.LIST:
            if exposure_ends_at is not None or banner_order is not None:
                raise serializers.ValidationError(
                    "목록 공지는 노출 종료 시각과 배너 순서를 설정할 수 없습니다."
                )
            return attrs
        if status != Notice.PublicationStatus.PUBLISHED:
            return attrs
        if exposure_ends_at is None:
            raise serializers.ValidationError({"exposure_ends_at": "노출 종료 시각을 입력해주세요."})
        if exposure_ends_at <= publish_at:
            raise serializers.ValidationError(
                {"exposure_ends_at": "노출 종료 시각은 게시 시각보다 늦어야 합니다."}
            )
        if exposure_type != Notice.ExposureType.HOME_BANNER:
            if banner_order is not None:
                raise serializers.ValidationError(
                    {"banner_order": "목록 공지에는 배너 순서를 설정할 수 없습니다."}
                )
            return attrs
        if not has_home_image:
            raise serializers.ValidationError(
                {"home_banner_image": "홈 배너에는 웹 홈 배너 이미지가 필요합니다."}
            )
        legacy_published_banner = (
            instance is not None
            and instance.status == Notice.PublicationStatus.PUBLISHED
            and instance.exposure_type == Notice.ExposureType.HOME_BANNER
            and not instance.mobile_image
            and uploaded_mobile_image is serializers.empty
            and not remove_mobile_image
        )
        if not has_mobile_image and not legacy_published_banner:
            raise serializers.ValidationError(
                {"mobile_image": "홈 배너에는 앱 공지 이미지가 필요합니다."}
            )
        if banner_order is None or not 1 <= banner_order <= 5:
            raise serializers.ValidationError({"banner_order": "배너 순서는 1~5 중 하나여야 합니다."})

        overlaps = Notice.objects.filter(
            status=Notice.PublicationStatus.PUBLISHED,
            exposure_type=Notice.ExposureType.HOME_BANNER,
            publish_at__lt=exposure_ends_at,
            exposure_ends_at__gt=publish_at,
        )
        if instance:
            overlaps = overlaps.exclude(pk=instance.pk)
        if overlaps.count() >= 5:
            raise serializers.ValidationError("같은 기간에 노출할 홈 배너는 최대 5개입니다.")
        return attrs

    def update(self, instance, validated_data):
        """교체하거나 삭제된 두 이미지의 기존 파일을 정리합니다."""
        remove_home_image = validated_data.pop("remove_home_banner_image", False)
        remove_mobile_image = validated_data.pop("remove_mobile_image", False)
        old_home_image = instance.home_banner_image if instance.home_banner_image else None
        old_mobile_image = instance.mobile_image if instance.mobile_image else None
        home_image_replaced = "home_banner_image" in validated_data
        mobile_image_replaced = "mobile_image" in validated_data
        if remove_home_image:
            validated_data["home_banner_image"] = None
        if remove_mobile_image:
            validated_data["mobile_image"] = None
        updated = super().update(instance, validated_data)
        if old_home_image and (remove_home_image or home_image_replaced):
            old_home_image.delete(save=False)
        if old_mobile_image and (remove_mobile_image or mobile_image_replaced):
            old_mobile_image.delete(save=False)
        return updated

    def create(self, validated_data):
        """모델 필드가 아닌 이미지 삭제 플래그를 제외하고 공지를 생성합니다."""
        validated_data.pop("remove_home_banner_image", None)
        validated_data.pop("remove_mobile_image", None)
        return super().create(validated_data)
