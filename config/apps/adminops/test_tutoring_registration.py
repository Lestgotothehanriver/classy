import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from config.apps.accounts.models import Instructor, Student, Subject
from config.apps.adminops.models import AdminActionLog
from config.apps.chat_app.models import ChatRoom
from config.apps.pending.models import PendingInstructor
from config.apps.tutoring.models import (
    CommissionInvoice,
    TutoringPost,
    TutoringRegistration,
    TutoringResource,
)

User = get_user_model()
PASSWORD = "Passw0rd!123"


class TutoringRegistrationAdminAPITests(APITestCase):
    LIST = "/admin-api/v1/tutoring-registrations/"

    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            FILE_UPLOAD_MAX_MEMORY_SIZE=0,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.admin = User.objects.create_user(
            username="root@example.com",
            email="root@example.com",
            user_name="루트관리자",
            password=PASSWORD,
        )
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_superuser", "is_staff"])
        self.admin_token = Token.objects.create(user=self.admin)

        self.student_user = User.objects.create_user(
            username="reg_student",
            email="student@example.com",
            user_name="등록학생",
            phone="010-1111-2222",
            password=PASSWORD,
            first_name="길동",
            last_name="홍",
        )
        self.instructor_user = User.objects.create_user(
            username="reg_instructor",
            email="teacher@example.com",
            user_name="등록강사",
            phone="010-3333-4444",
            password=PASSWORD,
            first_name="선생",
            last_name="김",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(
            user=self.instructor_user, university="Classy University"
        )
        # 강사 학력인증 상태 링크 노출 확인용.
        PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.VERIFIED,
        )
        self.subject = Subject.objects.create(number=3)
        self.post = TutoringPost.objects.create(student=self.student, title="수학")
        self.room = ChatRoom.objects.create(
            student=self.student,
            instructor=self.instructor,
            post=self.post,
            initiated_by=self.student_user,
        )
        self.submit_url = (
            f"/tutoring/resources/chatrooms/{self.room.pk}/my-registration/"
        )

    # ── fixtures ──────────────────────────────────────────────────────────
    def _submit_both(self):
        """양측 제출로 AWAITING_CONFIRMATION 상태 등록을 만든다."""
        student_client = APIClient()
        student_client.force_authenticate(self.student_user)
        instructor_client = APIClient()
        instructor_client.force_authenticate(self.instructor_user)

        student_client.put(
            self.submit_url,
            {
                "subject": "수학",
                "subjectIds": [self.subject.number],
                "startDate": "2026-07-20",
                "classType": "REGULAR",
                "firstMonthFee": 500000,
                "paybackAccount": {
                    "bankCode": "우리은행",
                    "accountNumber": "123-456-789012",
                    "accountHolder": "홍길동",
                },
            },
            format="json",
        )
        instructor_client.put(
            self.submit_url,
            {
                "subject": "수학",
                "subjectIds": [str(self.subject.number)],
                "startDate": "2026-07-20",
                "classType": "REGULAR",
                "firstMonthFee": "500000",
                "feeConfirmationFiles": [
                    SimpleUploadedFile("p1.jpg", b"one", content_type="image/jpeg"),
                    SimpleUploadedFile("p2.jpg", b"two", content_type="image/jpeg"),
                ],
            },
            format="multipart",
        )
        return TutoringRegistration.objects.get()

    def _bare_registration(self, *, suffix, commission):
        """정렬 테스트용: 앱 흐름 없이 인보이스만 붙인 최소 등록을 만든다."""
        s_user = User.objects.create_user(
            username=f"s_{suffix}", user_name=f"학생{suffix}", password=PASSWORD
        )
        i_user = User.objects.create_user(
            username=f"i_{suffix}", user_name=f"강사{suffix}", password=PASSWORD
        )
        student = Student.objects.create(user=s_user)
        instructor = Instructor.objects.create(user=i_user, university="U")
        post = TutoringPost.objects.create(student=student, title="영어")
        room = ChatRoom.objects.create(
            student=student, instructor=instructor, post=post, initiated_by=s_user
        )
        registration = TutoringRegistration.objects.create(
            student=s_user,
            instructor=i_user,
            chat_room=room,
            subject="영어",
            start_date="2026-08-01",
        )
        CommissionInvoice.objects.create(
            registration=registration,
            base_amount=commission * 10,
            commission_rate_bps=1000,
            commission_amount=commission,
        )
        return registration

    def as_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")

    def detail_url(self, pk):
        return f"{self.LIST}{pk}/"

    # ── 권한 ──────────────────────────────────────────────────────────────
    def test_requires_superuser(self):
        self.assertEqual(self.client.get(self.LIST).status_code, 401)

        plain = User.objects.create_user(
            username="plain", user_name="일반", password=PASSWORD
        )
        plain_token = Token.objects.create(user=plain)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {plain_token.key}")
        self.assertEqual(self.client.get(self.LIST).status_code, 403)

    # ── 목록/필터/검색/요약 ────────────────────────────────────────────────
    def test_list_and_summary(self):
        self._submit_both()
        self.as_admin()

        res = self.client.get(self.LIST)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        row = res.data["results"][0]
        self.assertEqual(row["contract_status"], "REGISTERED")
        self.assertEqual(row["attribute_validation_status"], "MATCHED")
        self.assertEqual(row["fee_payment_status"], "AWAITING_CONFIRMATION")
        self.assertEqual(row["commission_amount"], 75000)  # 500000 * 15%
        self.assertEqual(row["instructor_name"], "김선생")

        self.assertEqual(
            self.client.get(self.LIST, {"contract_status": "REGISTERED"}).data["count"],
            1,
        )
        self.assertEqual(
            self.client.get(self.LIST, {"contract_status": "ACTIVE"}).data["count"], 0
        )
        self.assertEqual(
            self.client.get(
                self.LIST, {"fee_payment_status": "AWAITING_CONFIRMATION"}
            ).data["count"],
            1,
        )
        self.assertEqual(self.client.get(self.LIST, {"q": "등록강사"}).data["count"], 1)
        self.assertEqual(self.client.get(self.LIST, {"q": "없는사람"}).data["count"], 0)

        summary = self.client.get(f"{self.LIST}summary/").data
        self.assertEqual(summary["REGISTERED"], 1)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["awaiting_confirmation"], 1)

    def test_ordering_by_commission_amount(self):
        self._submit_both()  # 수수료 75,000
        self._bare_registration(suffix="low", commission=30000)
        self.as_admin()

        desc = self.client.get(self.LIST, {"ordering": "-commission_amount"})
        self.assertEqual(
            [row["commission_amount"] for row in desc.data["results"]],
            [75000, 30000],
        )

        asc = self.client.get(self.LIST, {"ordering": "commission_amount"})
        self.assertEqual(
            [row["commission_amount"] for row in asc.data["results"]],
            [30000, 75000],
        )

    def test_detail_includes_contacts_account_and_submissions(self):
        registration = self._submit_both()
        self.as_admin()
        res = self.client.get(self.detail_url(registration.pk))
        self.assertEqual(res.status_code, 200)
        data = res.data

        self.assertEqual(data["instructor"]["email"], "teacher@example.com")
        self.assertEqual(data["instructor"]["phone"], "010-3333-4444")
        self.assertEqual(data["instructor"]["verification_status"], "VERIFIED")
        self.assertEqual(data["student"]["email"], "student@example.com")

        # 페이백 계좌는 전체(비마스킹) 노출.
        self.assertEqual(data["payback_account"]["account_number"], "123456789012")
        self.assertEqual(data["payback_account"]["account_holder"], "홍길동")

        self.assertEqual(len(data["submissions"]), 2)
        self.assertEqual(data["commission_invoice"]["commission_amount"], 75000)
        self.assertEqual(data["commission_invoice"]["commission_rate_bps"], 1500)
        self.assertIn("account_number", data["platform_account"])
        self.assertEqual(len(data["resource"]["files"]), 2)
        self.assertEqual(data["mismatched_fields"], [])

    # ── 수수료 확인 ────────────────────────────────────────────────────────
    def test_confirm_fee_activates_contract_and_logs(self):
        registration = self._submit_both()
        self.as_admin()
        res = self.client.post(
            f"{self.detail_url(registration.pk)}confirm-fee/", {}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["contract_status"], "ACTIVE")
        self.assertEqual(res.data["fee_payment_status"], "PAID")

        registration.refresh_from_db()
        self.assertEqual(registration.contract_status, "ACTIVE")
        self.assertEqual(CommissionInvoice.objects.get().status, "PAID")
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="tutoring_registration.confirm_fee",
                target_id=str(registration.pk),
            ).exists()
        )

    def test_confirm_non_awaiting_conflicts(self):
        registration = self._submit_both()
        self.as_admin()
        # 첫 확인은 성공.
        self.client.post(
            f"{self.detail_url(registration.pk)}confirm-fee/", {}, format="json"
        )
        # PAID 상태에서 재확인은 409.
        res = self.client.post(
            f"{self.detail_url(registration.pk)}confirm-fee/", {}, format="json"
        )
        self.assertEqual(res.status_code, 409)

    # ── 수수료 반려 ────────────────────────────────────────────────────────
    def test_reject_fee_fails_and_logs(self):
        registration = self._submit_both()
        self.as_admin()
        res = self.client.post(
            f"{self.detail_url(registration.pk)}reject-fee/",
            {"reason": "입금 미확인"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["fee_payment_status"], "FAILED")

        resource = TutoringResource.objects.get()
        self.assertEqual(resource.fee_payment_status, "FAILED")
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="tutoring_registration.reject_fee",
                target_id=str(registration.pk),
                reason="입금 미확인",
            ).exists()
        )

    # ── 증빙 보호 스트리밍 ─────────────────────────────────────────────────
    def test_document_streaming_and_not_found(self):
        registration = self._submit_both()
        file_id = TutoringResource.objects.get().files.first().pk
        self.as_admin()

        ok = self.client.get(
            f"{self.detail_url(registration.pk)}documents/{file_id}/"
        )
        self.assertEqual(ok.status_code, 200)
        self.assertIn("inline", ok["Content-Disposition"])
        # 스트리밍 파일 핸들을 닫아 임시 MEDIA_ROOT 정리가 막히지 않게 한다(Windows).
        ok.close()

        missing = self.client.get(
            f"{self.detail_url(registration.pk)}documents/999999/"
        )
        self.assertEqual(missing.status_code, 404)
