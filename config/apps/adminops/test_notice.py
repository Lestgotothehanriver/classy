import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from config.apps.adminops.models import AdminActionLog
from config.apps.notice.models import Notice


User = get_user_model()
_MEDIA_ROOT = tempfile.mkdtemp(prefix="notice_media_")


def make_user(email, *, superuser=False):
    """테스트용 일반 또는 슈퍼관리자 계정을 생성합니다."""
    user = User.objects.create_user(
        username=email,
        email=email,
        user_name=email,
        password="Passw0rd!123",
    )
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])
    return user


def banner_file(name="banner.png", *, width=300, height=100, content_type="image/png"):
    """[width]×[height] 비율의 메모리 배너 파일을 생성합니다."""
    content = BytesIO()
    Image.new("RGB", (width, height), color=(95, 101, 215)).save(content, "PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type=content_type)


def mobile_file(name="mobile.png", *, width=320, height=180, content_type="image/png"):
    """[width]×[height] 비율의 메모리 모바일 공지 이미지를 생성합니다."""
    return banner_file(
        name,
        width=width,
        height=height,
        content_type=content_type,
    )


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class NoticeAPITests(APITestCase):
    """공지 공개 API와 슈퍼관리자 운영 API를 검증합니다."""

    ADMIN_LIST = "/admin-api/v1/notices/"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.admin = make_user("notice-admin@example.com", superuser=True)
        self.user = make_user("notice-user@example.com")

    def as_admin(self):
        self.client.force_authenticate(self.admin)

    def payload(self, **overrides):
        now = timezone.now()
        values = {
            "title": "서비스 점검 안내",
            "summary": "더 안정적인 서비스 제공을 위한 점검입니다.",
            "content": "점검 시간에는 일부 서비스 이용이 제한됩니다.",
            "status": Notice.PublicationStatus.PUBLISHED,
            "publish_at": now.isoformat(),
            "exposure_type": Notice.ExposureType.LIST,
        }
        values.update(overrides)
        return values

    def create_published(self, **overrides):
        values = self.payload(**overrides)
        return Notice.objects.create(**values, created_by=self.admin, updated_by=self.admin)

    def test_admin_requires_authenticated_superuser(self):
        self.assertEqual(self.client.get(self.ADMIN_LIST).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.ADMIN_LIST).status_code, 403)

    def test_admin_creates_separate_home_and_mobile_images_and_logs_action(self):
        self.as_admin()
        response = self.client.post(
            self.ADMIN_LIST,
            self.payload(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=(timezone.now() + timedelta(days=1)).isoformat(),
                banner_order=1,
                home_banner_image=banner_file(),
                mobile_image=mobile_file(),
            ),
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["home_banner_image"].startswith("http"))
        self.assertTrue(response.data["mobile_image"].startswith("http"))
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="notice.create", target_type="Notice", target_id=str(response.data["id"])
            ).exists()
        )

    def test_banner_rejects_invalid_image_ratios_and_excess_concurrent_exposure(self):
        self.as_admin()
        invalid_ratio = self.client.post(
            self.ADMIN_LIST,
            self.payload(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=(timezone.now() + timedelta(days=1)).isoformat(),
                banner_order=1,
                home_banner_image=banner_file(width=100, height=100),
                mobile_image=mobile_file(),
            ),
            format="multipart",
        )
        self.assertEqual(invalid_ratio.status_code, 400)

        invalid_mobile_ratio = self.client.post(
            self.ADMIN_LIST,
            self.payload(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=(timezone.now() + timedelta(days=1)).isoformat(),
                banner_order=1,
                home_banner_image=banner_file(),
                mobile_image=mobile_file(width=300, height=100),
            ),
            format="multipart",
        )
        self.assertEqual(invalid_mobile_ratio.status_code, 400)

        oversized_image = SimpleUploadedFile(
            "oversized.png",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="image/png",
        )
        oversized = self.client.post(
            self.ADMIN_LIST,
            self.payload(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=(timezone.now() + timedelta(days=1)).isoformat(),
                banner_order=1,
                home_banner_image=oversized_image,
                mobile_image=mobile_file(),
            ),
            format="multipart",
        )
        self.assertEqual(oversized.status_code, 400)

        for order in range(1, 6):
            self.create_published(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=timezone.now() + timedelta(days=1),
                banner_order=order,
            )
        response = self.client.post(
            self.ADMIN_LIST,
            self.payload(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=(timezone.now() + timedelta(hours=12)).isoformat(),
                banner_order=5,
                home_banner_image=banner_file(),
                mobile_image=mobile_file(),
            ),
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_removes_home_and_mobile_images_independently(self):
        self.as_admin()
        created = self.client.post(
            self.ADMIN_LIST,
            self.payload(
                exposure_type=Notice.ExposureType.HOME_BANNER,
                exposure_ends_at=(timezone.now() + timedelta(days=1)).isoformat(),
                banner_order=1,
                home_banner_image=banner_file(),
                mobile_image=mobile_file(),
            ),
            format="multipart",
        )
        self.assertEqual(created.status_code, 201)
        response = self.client.patch(
            f"{self.ADMIN_LIST}{created.data['id']}",
            {"status": Notice.PublicationStatus.UNPUBLISHED, "remove_mobile_image": True},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data["home_banner_image"])
        self.assertIsNone(response.data["mobile_image"])

    def test_public_only_returns_currently_published_notices_and_active_exposure(self):
        published = self.create_published(title="게시 공지")
        self.create_published(title="예약 공지", publish_at=timezone.now() + timedelta(days=1))
        Notice.objects.create(
            title="초안 공지",
            summary="초안",
            content="초안",
            status=Notice.PublicationStatus.DRAFT,
        )
        active_banner = self.create_published(
            title="활성 배너",
            exposure_type=Notice.ExposureType.HOME_BANNER,
            exposure_ends_at=timezone.now() + timedelta(days=1),
            banner_order=1,
            home_banner_image=banner_file(),
        )
        self.create_published(
            title="종료 배너",
            exposure_type=Notice.ExposureType.HOME_BANNER,
            exposure_ends_at=timezone.now() - timedelta(minutes=1),
            banner_order=2,
        )

        self.client.force_authenticate(user=None)
        listing = self.client.get("/notices/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual({row["id"] for row in listing.data["results"]}, {published.id, active_banner.id, Notice.objects.get(title="종료 배너").id})
        self.assertEqual(self.client.get(f"/notices/{published.id}/").status_code, 200)
        exposure = self.client.get("/notices/exposure/").data
        self.assertEqual(exposure["banners"][0]["id"], active_banner.id)
        self.assertEqual(exposure["carousel"][0]["id"], active_banner.id)
        self.assertIn("home_banner_image", exposure["banners"][0])
        self.assertIn("mobile_image", exposure["banners"][0])
        self.assertEqual(
            exposure["banners"][0]["banner_image"],
            exposure["banners"][0]["home_banner_image"],
        )
        self.assertIsNone(exposure["banners"][0]["mobile_image"])

    def test_unpublish_hides_public_notice_and_records_log(self):
        self.as_admin()
        notice = self.create_published()
        response = self.client.post(f"{self.ADMIN_LIST}{notice.id}/unpublish/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f"/notices/{notice.id}/").status_code, 404)
        self.assertTrue(
            AdminActionLog.objects.filter(action="notice.unpublish", target_id=str(notice.id)).exists()
        )
