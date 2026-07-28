import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor
from config.apps.adminops.models import AdminActionLog
from config.apps.cash.models import Account, LectureRentalHistory, SettlementRecord
from config.apps.lecture.models import Lecture

User = get_user_model()
PASSWORD = "Passw0rd!123"
_MEDIA = tempfile.mkdtemp(prefix="settlement_media_")


def make_user(email, *, superuser=False, first="", last=""):
    user = User.objects.create_user(
        username=email, email=email, user_name=email, password=PASSWORD
    )
    changed = []
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        changed += ["is_superuser", "is_staff"]
    if first or last:
        user.first_name = first
        user.last_name = last
        changed += ["first_name", "last_name"]
    if changed:
        user.save(update_fields=changed)
    return user


@override_settings(MEDIA_ROOT=_MEDIA)
class SettlementAPITests(APITestCase):
    LIST = "/admin-api/v1/settlements/"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = make_user("root@example.com", superuser=True)
        self.admin_token = Token.objects.create(user=self.admin)

        self.teacher = make_user("teacher@example.com", first="선생", last="김")
        self.instructor = Instructor.objects.create(
            user=self.teacher,
            university="서울대학교",
            department="수학교육과",
            student_number="2019123",
        )
        self.account = Account.objects.create(
            instructor=self.instructor,
            bank="신한은행",
            account_number="110-123-456789",
            account_holder="김선생",
        )
        self.lecture = Lecture.objects.create(
            title="미적분 특강",
            price=1000,
            instructor=self.instructor,
            video=SimpleUploadedFile("v.mp4", b"fake", content_type="video/mp4"),
            thumbnail=SimpleUploadedFile("t.jpg", b"fake", content_type="image/jpeg"),
        )
        self.student = make_user("student@example.com")

        self.settlement = SettlementRecord.objects.create(
            instructor=self.instructor, amount=10000, status="PENDING"
        )
        # 정산에 연결된 대여 2건(정산 대상으로 마킹).
        self.rentals = [
            LectureRentalHistory.objects.create(
                lecture=self.lecture,
                student=self.student,
                purchased_cash=5000,
                remaining_cash=0,
                is_settled=True,
                settlement=self.settlement,
            )
            for _ in range(2)
        ]

    def as_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")

    def detail_url(self, pk):
        return f"{self.LIST}{pk}/"

    # ── 권한 ──────────────────────────────────────────────────────────────
    def test_requires_superuser(self):
        self.assertEqual(self.client.get(self.LIST).status_code, 401)

        plain = make_user("plain@example.com")
        plain_token = Token.objects.create(user=plain)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {plain_token.key}")
        self.assertEqual(self.client.get(self.LIST).status_code, 403)

    # ── 목록/필터/검색/요약 ────────────────────────────────────────────────
    def test_list_and_summary(self):
        self.as_admin()
        res = self.client.get(self.LIST)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        row = res.data["results"][0]
        self.assertEqual(row["amount"], 10000)
        self.assertEqual(row["platform_fee"], 2000)  # 20%
        self.assertEqual(row["payout_amount"], 8000)
        self.assertEqual(row["rental_count"], 2)

        self.assertEqual(self.client.get(self.LIST, {"status": "PENDING"}).data["count"], 1)
        self.assertEqual(self.client.get(self.LIST, {"status": "COMPLETED"}).data["count"], 0)
        self.assertEqual(self.client.get(self.LIST, {"q": "teacher"}).data["count"], 1)
        self.assertEqual(self.client.get(self.LIST, {"q": "없는사람"}).data["count"], 0)

        summary = self.client.get(f"{self.LIST}summary/").data
        self.assertEqual(summary["PENDING"], 1)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["pending_amount"], 10000)

    def test_detail_includes_account_and_rentals(self):
        self.as_admin()
        res = self.client.get(self.detail_url(self.settlement.pk))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["account_info"]["account_number"], "110-123-456789")
        self.assertEqual(res.data["account_info"]["bank"], "신한은행")
        self.assertEqual(len(res.data["rentals"]), 2)

    # ── 완료 ──────────────────────────────────────────────────────────────
    def test_complete_requires_reference(self):
        self.as_admin()
        res = self.client.post(f"{self.detail_url(self.settlement.pk)}complete/", {}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_complete_success(self):
        self.as_admin()
        res = self.client.post(
            f"{self.detail_url(self.settlement.pk)}complete/",
            {"payment_reference": "TRX-123", "admin_note": "송금완료"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "COMPLETED")
        self.assertEqual(res.data["payment_reference"], "TRX-123")

        self.settlement.refresh_from_db()
        self.assertEqual(self.settlement.status, "COMPLETED")
        self.assertIsNotNone(self.settlement.processed_at)
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="settlement.complete", target_id=str(self.settlement.pk)
            ).exists()
        )

    def test_complete_non_pending_conflicts(self):
        self.settlement.status = "COMPLETED"
        self.settlement.save(update_fields=["status"])
        self.as_admin()
        res = self.client.post(
            f"{self.detail_url(self.settlement.pk)}complete/",
            {"payment_reference": "TRX-999"},
            format="json",
        )
        self.assertEqual(res.status_code, 409)

    # ── 취소 ──────────────────────────────────────────────────────────────
    def test_cancel_rolls_back_rentals(self):
        self.as_admin()
        res = self.client.post(
            f"{self.detail_url(self.settlement.pk)}cancel/",
            {"reason": "계좌 오류"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "CANCELED")

        for rental in self.rentals:
            rental.refresh_from_db()
            self.assertFalse(rental.is_settled)
            self.assertIsNone(rental.settlement_id)

        self.assertTrue(
            AdminActionLog.objects.filter(
                action="settlement.cancel", target_id=str(self.settlement.pk)
            ).exists()
        )

    def test_cancel_completed_is_allowed(self):
        self.settlement.status = "COMPLETED"
        self.settlement.save(update_fields=["status"])
        self.as_admin()
        res = self.client.post(f"{self.detail_url(self.settlement.pk)}cancel/", {}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "CANCELED")

    def test_cancel_already_canceled_conflicts(self):
        self.settlement.status = "CANCELED"
        self.settlement.save(update_fields=["status"])
        self.as_admin()
        res = self.client.post(f"{self.detail_url(self.settlement.pk)}cancel/", {}, format="json")
        self.assertEqual(res.status_code, 409)
