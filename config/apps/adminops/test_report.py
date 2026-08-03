"""신고 관리(adminops) API 테스트.

가해자(reported_user) 중심 큐/케이스/처리/제재와 ``ReportCreateSerializer`` 의
source 도출·description 저장을 검증한다. 정산/성사 테스트와 동일한 셋업 패턴.
"""

import shutil
import tempfile
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor, UserSanction, recompute_ban_state
from config.apps.adminops.models import AdminActionLog
from config.apps.lecture.models import Comment, Lecture
from config.apps.report.models import (
    Report,
    ReportChoice,
    ReportSourceChoices,
    ReportStatusChoices,
)
from config.apps.report.serializers import ReportCreateSerializer

User = get_user_model()
PASSWORD = "Passw0rd!123"
_MEDIA = tempfile.mkdtemp(prefix="report_media_")


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


def add_report(
    reporter,
    reported,
    *,
    source=ReportSourceChoices.TEACHER_PROFILE,
    status=ReportStatusChoices.PENDING,
    reasons=("other",),
):
    report = Report.objects.create(
        reporter=reporter, reported_user=reported, source=source, status=status
    )
    for reason in reasons:
        ReportChoice.objects.create(report=report, content=reason)
    return report


@override_settings(MEDIA_ROOT=_MEDIA)
class ReportQueueAPITests(APITestCase):
    LIST = "/admin-api/v1/reports/"
    SUMMARY = "/admin-api/v1/reports/summary/"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = make_user("root@example.com", superuser=True)
        self.admin_token = Token.objects.create(user=self.admin)

        self.offender = make_user("bad@example.com", first="철수", last="김")
        self.r1 = make_user("rep1@example.com")
        self.r2 = make_user("rep2@example.com")

        # 미처리 2건(고유 신고자 2명) + 조치완료 1건 → total=3, pending=2, effective=1
        add_report(self.r1, self.offender, status=ReportStatusChoices.PENDING)
        add_report(self.r2, self.offender, status=ReportStatusChoices.PENDING,
                   source=ReportSourceChoices.CHAT)
        add_report(self.r1, self.offender, status=ReportStatusChoices.RESOLVED)

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    # ------------------------------------------------------------------

    def test_requires_superadmin(self):
        normal = make_user("normal@example.com")
        token = Token.objects.create(user=normal)
        self.auth(token)
        self.assertEqual(self.client.get(self.LIST).status_code, 403)

    def test_queue_aggregates_counts(self):
        self.auth(self.admin_token)
        res = self.client.get(self.LIST)
        self.assertEqual(res.status_code, 200)
        rows = {row["user_id"]: row for row in res.data["results"]}
        self.assertIn(self.offender.pk, rows)
        row = rows[self.offender.pk]
        self.assertEqual(row["total_count"], 3)
        self.assertEqual(row["pending_count"], 2)
        self.assertEqual(row["effective_count"], 1)
        self.assertEqual(row["unique_reporters"], 2)
        self.assertFalse(row["is_banned"])

    def test_source_filter(self):
        self.auth(self.admin_token)
        res = self.client.get(self.LIST, {"source": ReportSourceChoices.CHAT})
        self.assertEqual(res.status_code, 200)
        ids = {row["user_id"] for row in res.data["results"]}
        self.assertIn(self.offender.pk, ids)
        # 채팅 신고가 없는 유저는 나오지 않는다.
        other = make_user("clean@example.com")
        add_report(self.r1, other, source=ReportSourceChoices.LECTURE)
        res2 = self.client.get(self.LIST, {"source": ReportSourceChoices.CHAT})
        self.assertNotIn(other.pk, {row["user_id"] for row in res2.data["results"]})

    def test_summary(self):
        self.auth(self.admin_token)
        res = self.client.get(self.SUMMARY)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data[ReportStatusChoices.PENDING], 2)
        self.assertEqual(res.data[ReportStatusChoices.RESOLVED], 1)
        self.assertEqual(res.data["total"], 3)
        self.assertEqual(res.data["reported_users"], 1)

    def test_case_detail_counts_and_recommendation(self):
        self.auth(self.admin_token)
        res = self.client.get(f"/admin-api/v1/reports/users/{self.offender.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["counts"]["total"], 3)
        self.assertEqual(res.data["counts"]["effective"], 1)
        self.assertEqual(res.data["counts"]["unique_reporters"], 2)
        # 최초 제재(이력 없음, effective<3) → 경고 추천
        self.assertEqual(res.data["recommended_sanction"], UserSanction.Type.WARNING)
        # source 별로 그룹핑된다.
        sources = {g["source"] for g in res.data["reports_by_source"]}
        self.assertIn(ReportSourceChoices.CHAT, sources)

    def test_resolve_dismiss_batch_closes(self):
        self.auth(self.admin_token)
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.offender.pk}/resolve/",
            {"outcome": ReportStatusChoices.DISMISSED, "reason": "악성 신고"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        # 미처리 2건이 모두 DISMISSED 로 종결(기존 RESOLVED 1건은 그대로).
        self.assertEqual(
            Report.objects.filter(
                reported_user=self.offender, status=ReportStatusChoices.DISMISSED
            ).count(),
            2,
        )
        self.assertFalse(self.offender.reports_received.filter(
            status__in=[ReportStatusChoices.PENDING, ReportStatusChoices.IN_REVIEW]
        ).exists())

    def test_resolve_with_suspension_bans_user(self):
        self.auth(self.admin_token)
        expires = (timezone.now() + timedelta(days=7)).isoformat()
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.offender.pk}/resolve/",
            {
                "outcome": ReportStatusChoices.RESOLVED,
                "reason": "부적절",
                "sanction": {"type": UserSanction.Type.SUSPENSION, "expires_at": expires},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.offender.refresh_from_db()
        self.assertTrue(self.offender.is_banned)
        self.assertEqual(
            UserSanction.objects.filter(target_user=self.offender, is_active=True).count(),
            1,
        )
        # 감사 로그: 제재 + 종결 기록
        actions = set(
            AdminActionLog.objects.filter(target_id=str(self.offender.pk))
            .values_list("action", flat=True)
        )
        self.assertIn("report.sanction", actions)
        self.assertIn("report.resolve", actions)

    def test_resolve_conflict_when_nothing_open(self):
        # 모든 신고를 먼저 종결시켜 미처리 0으로 만든다.
        Report.objects.filter(reported_user=self.offender).update(
            status=ReportStatusChoices.DISMISSED
        )
        self.auth(self.admin_token)
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.offender.pk}/resolve/",
            {"outcome": ReportStatusChoices.RESOLVED},
            format="json",
        )
        self.assertEqual(res.status_code, 409)

    def test_in_review_and_guard(self):
        self.auth(self.admin_token)
        report = self.offender.reports_received.filter(
            status=ReportStatusChoices.PENDING
        ).first()
        res = self.client.post(f"/admin-api/v1/reports/{report.pk}/in-review/")
        self.assertEqual(res.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, ReportStatusChoices.IN_REVIEW)
        # 이미 IN_REVIEW → 다시 보류 전환 불가(409)
        res2 = self.client.post(f"/admin-api/v1/reports/{report.pk}/in-review/")
        self.assertEqual(res2.status_code, 409)

    def test_sanction_and_lift_recomputes_ban(self):
        self.auth(self.admin_token)
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.offender.pk}/sanction/",
            {"type": UserSanction.Type.PERMANENT_BAN, "reason": "중대 위반"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.offender.refresh_from_db()
        self.assertTrue(self.offender.is_banned)

        sanction = UserSanction.objects.get(target_user=self.offender, is_active=True)
        res2 = self.client.post(
            f"/admin-api/v1/reports/sanctions/{sanction.pk}/lift/",
            {"reason": "오조치"},
            format="json",
        )
        self.assertEqual(res2.status_code, 200)
        self.offender.refresh_from_db()
        self.assertFalse(self.offender.is_banned)


class RecomputeBanStateTests(TestCase):
    """만료·해제에 따른 is_banned 재계산 단위 검증."""

    def test_expired_suspension_lifts_ban(self):
        user = make_user("u@example.com")
        # 미래 만료 정지 → 밴
        UserSanction.objects.create(
            target_user=user,
            type=UserSanction.Type.SUSPENSION,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(recompute_ban_state(user))

        # 만료된 정지만 남으면 밴 해제
        UserSanction.objects.filter(target_user=user).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        self.assertFalse(recompute_ban_state(user))
        user.refresh_from_db()
        self.assertFalse(user.is_banned)

    def test_warning_does_not_ban(self):
        user = make_user("w@example.com")
        UserSanction.objects.create(target_user=user, type=UserSanction.Type.WARNING)
        self.assertFalse(recompute_ban_state(user))


@override_settings(MEDIA_ROOT=_MEDIA)
class ReportCreateSerializerTests(TestCase):
    """앱 신고 생성: description 저장 + source 기반 소유자 도출."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.reporter = make_user("reporter@example.com")
        self.teacher = make_user("teacher@example.com", first="영희", last="이")
        self.instructor = Instructor.objects.create(
            user=self.teacher, university="연세대학교", department="영문과"
        )

    def _create(self, data, reporter=None):
        serializer = ReportCreateSerializer(
            data=data,
            context={"request": SimpleNamespace(user=reporter or self.reporter)},
        )
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def test_legacy_path_saves_description(self):
        report = self._create(
            {
                "reported_user": self.teacher.pk,
                "description": "무례합니다",
                "choices": ["abusive_language"],
            }
        )
        self.assertEqual(report.description, "무례합니다")
        self.assertEqual(report.reported_user_id, self.teacher.pk)

    def test_teacher_profile_source_derives_owner(self):
        report = self._create(
            {
                "source": "teacher_profile",
                "target_id": self.instructor.pk,
                "choices": ["other"],
            }
        )
        self.assertEqual(report.source, ReportSourceChoices.TEACHER_PROFILE)
        self.assertEqual(report.reported_user_id, self.teacher.pk)
        self.assertEqual(report.content_object, self.instructor)

    def test_comment_source_derives_author(self):
        lecture = Lecture.objects.create(
            title="문법 강의",
            instructor=self.instructor,
            video=SimpleUploadedFile("v.mp4", b"x", content_type="video/mp4"),
            thumbnail=SimpleUploadedFile("t.jpg", b"x", content_type="image/jpeg"),
        )
        author = make_user("commenter@example.com")
        comment = Comment.objects.create(
            lecture=lecture, author=author, content="스팸 댓글"
        )
        report = self._create(
            {"source": "comment", "target_id": comment.pk, "choices": ["other"]}
        )
        self.assertEqual(report.reported_user_id, author.pk)
        self.assertEqual(report.content_object, comment)

    def test_self_report_blocked(self):
        from rest_framework.exceptions import ValidationError as DRFValidationError

        with self.assertRaises(DRFValidationError):
            self._create(
                {
                    "source": "teacher_profile",
                    "target_id": self.instructor.pk,
                    "choices": ["other"],
                },
                reporter=self.teacher,
            )


@override_settings(MEDIA_ROOT=_MEDIA)
class ContentActionTests(APITestCase):
    """Phase 2: 콘텐츠 조치(차단/해제) + 앱 쿼리 반영 + 댓글 tombstone."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = make_user("root2@example.com", superuser=True)
        self.admin_token = Token.objects.create(user=self.admin)

        self.teacher = make_user("teach2@example.com", first="영희", last="이")
        self.instructor = Instructor.objects.create(
            user=self.teacher, university="연세대학교", department="영문과"
        )
        self.lecture = Lecture.objects.create(
            title="문법 강의",
            instructor=self.instructor,
            video=SimpleUploadedFile("v.mp4", b"x", content_type="video/mp4"),
            thumbnail=SimpleUploadedFile("t.jpg", b"x", content_type="image/jpeg"),
        )
        self.reporter = make_user("rep2@example.com")
        # source=lecture 신고(content_object=lecture, reported_user=업로더)
        self.report = Report.objects.create(
            reporter=self.reporter,
            reported_user=self.teacher,
            source=ReportSourceChoices.LECTURE,
        )
        self.report.content_object = self.lecture
        self.report.save()
        ReportChoice.objects.create(report=self.report, content="inappropriate_content")

    def admin_auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")

    def test_block_content_endpoint_and_case_reflection(self):
        self.admin_auth()
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.teacher.pk}/content/",
            {"content_type": "lecture", "object_id": self.lecture.pk, "action": "block"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.lecture.refresh_from_db()
        self.assertIsNotNone(self.lecture.admin_blocked_at)
        self.assertEqual(self.lecture.admin_blocked_by_id, self.admin.pk)
        group = next(
            g for g in res.data["reports_by_source"]
            if g["source"] == ReportSourceChoices.LECTURE
        )
        self.assertTrue(group["reports"][0]["content"]["is_blocked"])

    def test_unblock_content_endpoint(self):
        self.admin_auth()
        self.lecture.admin_blocked_at = timezone.now()
        self.lecture.admin_blocked_by = self.admin
        self.lecture.save(update_fields=["admin_blocked_at", "admin_blocked_by"])
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.teacher.pk}/content/",
            {"content_type": "lecture", "object_id": self.lecture.pk, "action": "unblock"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.lecture.refresh_from_db()
        self.assertIsNone(self.lecture.admin_blocked_at)

    def test_resolve_case_with_content_action(self):
        self.admin_auth()
        res = self.client.post(
            f"/admin-api/v1/reports/users/{self.teacher.pk}/resolve/",
            {
                "outcome": ReportStatusChoices.RESOLVED,
                "content_actions": [
                    {"content_type": "lecture", "object_id": self.lecture.pk, "action": "block"}
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.lecture.refresh_from_db()
        self.assertIsNotNone(self.lecture.admin_blocked_at)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ReportStatusChoices.RESOLVED)

    def test_blocked_lecture_hidden_from_browse(self):
        # 차단 전에는 브라우즈에 노출, 차단 후 제외된다.
        token = Token.objects.create(user=self.reporter)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        def lecture_ids():
            res = self.client.get("/lectures/")
            self.assertEqual(res.status_code, 200)
            rows = res.data["results"] if isinstance(res.data, dict) else res.data
            return {row["id"] for row in rows}

        self.assertIn(self.lecture.pk, lecture_ids())
        self.lecture.admin_blocked_at = timezone.now()
        self.lecture.save(update_fields=["admin_blocked_at"])
        self.assertNotIn(self.lecture.pk, lecture_ids())

    def test_resume_sales_blocked_for_admin_blocked_lecture(self):
        # 관리자 차단 강의는 강사가 판매를 재개할 수 없다(403).
        self.lecture.is_active = False
        self.lecture.admin_blocked_at = timezone.now()
        self.lecture.save(update_fields=["is_active", "admin_blocked_at"])
        token = Token.objects.create(user=self.teacher)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        res = self.client.post(f"/lectures/write/{self.lecture.pk}/resume-sales/")
        self.assertEqual(res.status_code, 403)
        self.lecture.refresh_from_db()
        self.assertFalse(self.lecture.is_active)

    def test_comment_tombstone_masking(self):
        from config.apps.adminops.services import report as svc
        from config.apps.lecture.serializers import CommentSerializer

        author = make_user("commenter2@example.com")
        comment = Comment.objects.create(
            lecture=self.lecture, author=author, content="원래 댓글 내용"
        )
        svc.block_content(comment, admin=self.admin)
        comment.refresh_from_db()
        self.assertTrue(comment.is_blocked)
        data = CommentSerializer(comment).data
        self.assertTrue(data["is_blocked"])
        self.assertEqual(data["content"], "신고 처리된 댓글입니다.")
