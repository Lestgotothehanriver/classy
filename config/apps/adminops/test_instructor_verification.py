import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor
from config.apps.adminops.models import AdminActionLog
from config.apps.pending.models import File, PendingInstructor

User = get_user_model()
PASSWORD = "Passw0rd!123"
_MEDIA = tempfile.mkdtemp(prefix="verif_media_")


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
class InstructorVerificationAPITests(APITestCase):
    LIST = "/admin-api/v1/instructor-verifications/"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = make_user("root@example.com", superuser=True)
        self.admin_token = Token.objects.create(user=self.admin)

        self.applicant = make_user("teacher@example.com", first="김", last="선생")
        self.instructor = Instructor.objects.create(
            user=self.applicant,
            university="서울대학교",
            department="수학교육과",
            student_number="2019123",
        )
        self.pending = PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.PENDING,
        )
        self.doc = File.objects.create(
            pending_instructor=self.pending,
            pending_file=SimpleUploadedFile("cert.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        )

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

    # ── 목록/필터/검색 ────────────────────────────────────────────────────
    def test_list_filter_and_search(self):
        self.as_admin()
        res = self.client.get(self.LIST)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        row = res.data["results"][0]
        self.assertEqual(row["real_name"], "김선생")
        self.assertEqual(row["file_count"], 1)

        self.assertEqual(self.client.get(self.LIST, {"status": "PENDING"}).data["count"], 1)
        self.assertEqual(self.client.get(self.LIST, {"status": "VERIFIED"}).data["count"], 0)
        self.assertEqual(self.client.get(self.LIST, {"q": "서울대"}).data["count"], 1)
        self.assertEqual(self.client.get(self.LIST, {"q": "김선생"}).data["count"], 1)
        self.assertEqual(self.client.get(self.LIST, {"q": "없는대학"}).data["count"], 0)

    # ── 상세 (문서 raw URL 미노출) ────────────────────────────────────────
    def test_detail_lists_documents_without_raw_url(self):
        self.as_admin()
        res = self.client.get(self.detail_url(self.pending.pk))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["documents"]), 1)
        doc = res.data["documents"][0]
        self.assertEqual(doc["id"], self.doc.pk)
        self.assertNotIn("url", doc)
        self.assertNotIn("pending_file", doc)

    # ── 승인 ──────────────────────────────────────────────────────────────
    def test_approve(self):
        self.as_admin()
        res = self.client.post(self.detail_url(self.pending.pk) + "approve/")
        self.assertEqual(res.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingInstructor.Status.VERIFIED)
        self.assertEqual(self.pending.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(self.pending.reviewed_at)
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="instructor_verification.approve",
                target_type="PendingInstructor",
                target_id=str(self.pending.pk),
            ).exists()
        )

    def test_approve_non_pending_conflicts(self):
        self.pending.status = PendingInstructor.Status.VERIFIED
        self.pending.save(update_fields=["status"])
        self.as_admin()
        res = self.client.post(self.detail_url(self.pending.pk) + "approve/")
        self.assertEqual(res.status_code, 409)

    # ── 반려 ──────────────────────────────────────────────────────────────
    def test_reject_requires_reason(self):
        self.as_admin()
        res = self.client.post(self.detail_url(self.pending.pk) + "reject/", {"reason": "   "}, format="json")
        self.assertEqual(res.status_code, 400)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingInstructor.Status.PENDING)

    def test_reject(self):
        self.as_admin()
        res = self.client.post(
            self.detail_url(self.pending.pk) + "reject/",
            {"reason": "제출 서류가 불명확합니다."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingInstructor.Status.SUSPENDED)
        self.assertEqual(self.pending.rejection_reason, "제출 서류가 불명확합니다.")
        self.assertEqual(self.pending.reviewed_by_id, self.admin.id)
        log = AdminActionLog.objects.get(action="instructor_verification.reject")
        self.assertEqual(log.reason, "제출 서류가 불명확합니다.")

    def test_reject_non_pending_conflicts(self):
        self.pending.status = PendingInstructor.Status.VERIFIED
        self.pending.save(update_fields=["status"])
        self.as_admin()
        res = self.client.post(
            self.detail_url(self.pending.pk) + "reject/", {"reason": "사유"}, format="json"
        )
        self.assertEqual(res.status_code, 409)

    # ── 문서 스트리밍 보안 ────────────────────────────────────────────────
    def test_document_streaming_permission_and_inline(self):
        doc_url = f"{self.detail_url(self.pending.pk)}documents/{self.doc.pk}/"

        self.assertEqual(self.client.get(doc_url).status_code, 401)  # 익명

        plain = make_user("plain2@example.com")
        plain_token = Token.objects.create(user=plain)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {plain_token.key}")
        self.assertEqual(self.client.get(doc_url).status_code, 403)  # 비-슈퍼

        self.as_admin()
        res = self.client.get(doc_url)
        self.assertEqual(res.status_code, 200)
        self.assertIn("inline", res.headers.get("Content-Disposition", ""))

    def test_document_mismatched_pending_returns_404(self):
        other_applicant = make_user("other@example.com")
        other_instructor = Instructor.objects.create(user=other_applicant, university="연세대")
        other_pending = PendingInstructor.objects.create(instructor_profile=other_instructor)
        self.as_admin()
        # self.doc 은 self.pending 소속인데 other_pending 경로로 접근 → 404
        url = f"{self.detail_url(other_pending.pk)}documents/{self.doc.pk}/"
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_direct_media_files_access_blocked(self):
        # raw 미디어 경로 직접 접근은 차단(404).
        self.assertEqual(self.client.get(f"/media/{self.doc.pending_file.name}").status_code, 404)


@override_settings(MEDIA_ROOT=_MEDIA)
class ReuploadResetTests(APITestCase):
    UPLOAD = "/pending/upload/"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def test_reupload_resets_review_fields(self):
        applicant = make_user("reup@example.com")
        instructor = Instructor.objects.create(user=applicant, university="고려대")
        reviewer = make_user("reviewer@example.com", superuser=True)
        pending = PendingInstructor.objects.create(
            instructor_profile=instructor,
            status=PendingInstructor.Status.SUSPENDED,
            rejection_reason="이전 반려 사유",
            reviewed_by=reviewer,
        )
        File.objects.create(
            pending_instructor=pending,
            pending_file=SimpleUploadedFile("old.pdf", b"old", content_type="application/pdf"),
        )

        token = Token.objects.create(user=applicant)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        res = self.client.post(
            self.UPLOAD,
            {"files": SimpleUploadedFile("new.pdf", b"new", content_type="application/pdf")},
            format="multipart",
        )
        self.assertEqual(res.status_code, 200)

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingInstructor.Status.PENDING)
        self.assertEqual(pending.rejection_reason, "")
        self.assertIsNone(pending.reviewed_by_id)
        self.assertIsNone(pending.reviewed_at)
