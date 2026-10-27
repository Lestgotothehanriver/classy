from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from config.apps.accounts.models import Instructor, Student
from config.apps.cash.models import LectureRentalHistory
from config.apps.lecture.models import Comment, Lecture
from config.apps.lecture.serializers import LectureListSerializer
from config.apps.notification.models import Notification
from config.apps.lecture.utils import extract_video_duration_seconds
from config.apps.lecture.utils import calculate_sample_preview_duration_seconds


User = get_user_model()


class OfficialCreatorLectureSerializerTests(TestCase):
    """공식 계정 강의의 공개 프로필 응답을 검증한다."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="official-lecture-creator",
            user_name="클래씨 강의",
        )
        self.user.profile_image = "profile_images/lecture-official-profile.png"
        self.user.save(update_fields=["profile_image"])
        self.instructor = Instructor.objects.create(
            user=self.user,
            university="비공개 대학교",
            department="비공개 학과",
            student_number="20260002",
            instruction="비공개 소개",
            is_official_creator=True,
        )
        self.lecture = Lecture.objects.create(
            instructor=self.instructor,
            title="공식 강의",
            price=0,
        )

    def test_official_lecture_exposes_django_managed_public_profile(self):
        """강의 응답은 이름·이미지를 보존하고 나머지 개인 정보만 숨긴다."""
        data = LectureListSerializer(self.lecture).data
        instructor = data["instructor"]

        self.assertEqual(data["instructor_name"], self.user.user_name)
        self.assertEqual(instructor["user_name"], self.user.user_name)
        self.assertTrue(
            instructor["profile_image"].endswith(self.user.profile_image.url)
        )
        self.assertEqual(instructor["university"], "")
        self.assertEqual(instructor["department"], "")
        self.assertEqual(instructor["student_number"], "")
        self.assertEqual(instructor["instruction"], "")


class LectureDurationExtractionTests(TestCase):
    """ffprobe 결과가 앱·웹과 같은 초 단위 버림 규칙을 따르는지 검증합니다."""

    def test_fractional_duration_is_truncated_to_seconds(self):
        """9.9초 영상은 플레이어 표기와 동일하게 9초로 저장합니다."""
        with (
            patch("config.apps.lecture.utils.shutil.which", return_value="ffprobe"),
            patch(
                "config.apps.lecture.utils.subprocess.run",
                return_value=SimpleNamespace(stdout="9.9\n"),
            ),
        ):
            self.assertEqual(extract_video_duration_seconds("video.mp4"), 9)

    def test_paid_sample_preview_duration_policy(self):
        self.assertEqual(calculate_sample_preview_duration_seconds(4), 1)
        self.assertEqual(calculate_sample_preview_duration_seconds(299), 59)
        self.assertEqual(calculate_sample_preview_duration_seconds(300), 60)


class LectureSamplePreviewApiTests(TestCase):
    """A-specific samples must not replace ordinary preview lectures."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username="sample-owner", user_name="sample-owner")
        self.student = User.objects.create_user(username="sample-student", user_name="sample-student")
        self.instructor = Instructor.objects.create(user=self.owner, university="Test")
        self.paid = Lecture.objects.create(
            instructor=self.instructor,
            title="Paid A",
            price=1000,
            sample_preview="lectures/sample_previews/a-sample.mp4",
            sample_preview_duration=60,
        )
        self.ordinary_preview = Lecture.objects.create(
            instructor=self.instructor,
            title="Ordinary B",
            price=0,
            is_preview=True,
        )

    def test_detail_exposes_only_sample_metadata_and_keeps_ordinary_preview(self):
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("lecture-detail", args=[self.paid.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["sample_preview"], {"duration_seconds": 60})
        self.assertEqual(response.data["preview_video"]["id"], self.ordinary_preview.id)
        self.assertNotIn("sample_preview", response.data["lecture_info"])

    def test_sample_preview_endpoint_requires_authentication_and_returns_a_clip(self):
        url = reverse("lecture-sample-preview", args=[self.paid.id])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.student)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.paid.id)
        self.assertEqual(response.data["duration_seconds"], 60)

    def test_sample_preview_endpoint_returns_404_when_a_paid_lecture_has_no_clip(self):
        self.paid.sample_preview = None
        self.paid.sample_preview_duration = 0
        self.paid.save(update_fields=["sample_preview", "sample_preview_duration"])
        self.client.force_authenticate(self.student)

        response = self.client.get(
            reverse("lecture-sample-preview", args=[self.paid.id])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_ordinary_preview_stays_in_the_lecture_list(self):
        response = self.client.get(reverse("lecture-list"))
        self.assertIn(self.ordinary_preview.id, [item["id"] for item in response.data["results"]])
        self.assertNotIn("sample_preview", response.data["results"][0])


class LectureCommentPermissionTests(TestCase):
    """강의 댓글 조회/작성/수정/삭제 권한 정책을 검증합니다."""

    def setUp(self):
        self.client = APIClient()
        self.owner_user = User.objects.create_user(
            username="owner",
            password="pw",
            user_name="owner",
        )
        self.student_user = User.objects.create_user(
            username="student",
            password="pw",
            user_name="student",
        )
        self.other_user = User.objects.create_user(
            username="other",
            password="pw",
            user_name="other",
        )
        self.instructor = Instructor.objects.create(
            user=self.owner_user,
            university="Test Univ",
        )
        Student.objects.create(user=self.student_user)
        Student.objects.create(user=self.other_user)
        self.paid_lecture = Lecture.objects.create(
            instructor=self.instructor,
            title="Paid Lecture",
            price=3000,
        )
        self.free_lecture = Lecture.objects.create(
            instructor=self.instructor,
            title="Free Lecture",
            price=0,
        )

    def _comment_url(self, lecture):
        return reverse("comment-list-create", args=[lecture.id])

    def _comment_detail_url(self, comment):
        return reverse("comment-update-delete", args=[comment.id])

    def _create_rental(self, user, lecture, *, expired=False):
        rental = LectureRentalHistory.objects.create(
            lecture=lecture,
            student=user,
            purchased_cash=lecture.price,
            remaining_cash=0,
        )
        if expired:
            rental.expiration_date = timezone.now() - timedelta(days=1)
            rental.save(update_fields=["expiration_date"])
        return rental

    def test_comment_list_is_public(self):
        Comment.objects.create(
            lecture=self.paid_lecture,
            author=self.owner_user,
            content="public comment",
        )

        response = self.client.get(self._comment_url(self.paid_lecture))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)

    def test_paid_lecture_rejects_logged_in_user_without_valid_rental(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            self._comment_url(self.paid_lecture),
            {"content": "no rental"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Comment.objects.filter(content="no rental").exists())

    def test_paid_lecture_allows_valid_renter_to_comment(self):
        self._create_rental(self.student_user, self.paid_lecture)
        self.client.force_authenticate(user=self.student_user)

        response = self.client.post(
            self._comment_url(self.paid_lecture),
            {"content": "valid renter"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Comment.objects.filter(content="valid renter").exists())

    def test_paid_lecture_allows_owner_to_comment(self):
        self.client.force_authenticate(user=self.owner_user)

        response = self.client.post(
            self._comment_url(self.paid_lecture),
            {"content": "owner comment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Comment.objects.filter(content="owner comment").exists())

    def test_free_lecture_allows_authenticated_user_without_rental(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            self._comment_url(self.free_lecture),
            {"content": "free lecture comment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Comment.objects.filter(content="free lecture comment").exists()
        )

    def test_expired_renter_cannot_update_or_delete_own_paid_comment(self):
        self._create_rental(self.student_user, self.paid_lecture, expired=True)
        comment = Comment.objects.create(
            lecture=self.paid_lecture,
            author=self.student_user,
            content="old comment",
        )
        self.client.force_authenticate(user=self.student_user)

        update_response = self.client.patch(
            self._comment_detail_url(comment),
            {"content": "edited"},
            format="json",
        )
        delete_response = self.client.delete(self._comment_detail_url(comment))

        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)
        comment.refresh_from_db()
        self.assertEqual(comment.content, "old comment")


class LectureCommentNotificationTests(TestCase):
    """영상 댓글과 대댓글의 역할별 알림 계약을 검증한다."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="lecture-owner",
            user_name="영상주인",
        )
        self.commenter = User.objects.create_user(
            username="commenter",
            user_name="댓글작성자",
        )
        self.replier = User.objects.create_user(
            username="replier",
            user_name="답글작성자",
        )
        self.instructor = Instructor.objects.create(
            user=self.owner,
            university="Test Univ",
        )
        Student.objects.create(user=self.commenter)
        Student.objects.create(user=self.replier)
        self.lecture = Lecture.objects.create(
            instructor=self.instructor,
            title="Free Lecture",
            price=0,
        )

    def _comment_url(self):
        return reverse("comment-list-create", args=[self.lecture.id])

    def _post_comment(self, user, payload):
        self.client.force_authenticate(user=user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self._comment_url(), payload, format="json")

    @patch("config.apps.notification.fcm.send_push_to_user")
    def test_comment_notifies_only_lecture_owner(self, send_push):
        response = self._post_comment(
            self.commenter,
            {"content": "강의가 좋아요", "author_role": "student"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get()
        self.assertEqual(notification.user_id, self.owner.id)
        self.assertEqual(notification.type, "lecture_comment")
        self.assertEqual(notification.role, "instructor")
        self.assertEqual(notification.title, "영상주인님의 영상에 댓글이 달렸어요.")
        self.assertEqual(notification.body, "댓글작성자: 강의가 좋아요")
        self.assertEqual(
            notification.data,
            {"lecture_id": str(self.lecture.id), "comment_id": str(response.data["id"])},
        )
        send_push.assert_called_once()

    @patch("config.apps.notification.fcm.send_push_to_user")
    def test_reply_notifies_thread_author_in_parent_role(self, send_push):
        parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.commenter,
            author_role="student",
            content="원댓글",
        )

        response = self._post_comment(
            self.replier,
            {
                "content": "답글이에요",
                "parent": parent.id,
                "author_role": "student",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get()
        self.assertEqual(notification.user_id, self.commenter.id)
        self.assertEqual(notification.type, "lecture_comment_reply")
        self.assertEqual(notification.role, "student")
        self.assertEqual(notification.title, "댓글작성자 님의 댓글에 댓글이 달렸어요.")
        self.assertEqual(notification.body, "답글작성자: 답글이에요")
        self.assertEqual(
            notification.data,
            {
                "lecture_id": str(self.lecture.id),
                "comment_id": str(response.data["id"]),
                "parent_comment_id": str(parent.id),
                "reply_to_comment_id": str(parent.id),
            },
        )
        send_push.assert_called_once()

    @patch("config.apps.notification.fcm.send_push_to_user")
    def test_reply_to_reply_notifies_direct_target_and_thread_author(self, send_push):
        parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.commenter,
            author_role="student",
            content="원댓글",
        )
        direct_target = Comment.objects.create(
            lecture=self.lecture,
            author=self.replier,
            author_role="student",
            parent=parent,
            content="첫 답글",
        )

        response = self._post_comment(
            self.owner,
            {
                "content": "답글에 답글이에요",
                "parent": parent.id,
                "reply_to": direct_target.id,
                "author_role": "instructor",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["parent"], parent.id)
        self.assertEqual(response.data["reply_to"], direct_target.id)
        self.assertEqual(response.data["referenced_person"], self.replier.id)
        self.assertEqual(response.data["referenced_person_name"], "답글작성자")
        self.assertEqual(Notification.objects.count(), 2)
        direct_target_notification = Notification.objects.get(user=self.replier)
        thread_author_notification = Notification.objects.get(user=self.commenter)
        self.assertEqual(direct_target_notification.role, "student")
        self.assertEqual(thread_author_notification.role, "student")
        self.assertEqual(
            direct_target_notification.title,
            "답글작성자 님의 댓글에 댓글이 달렸어요.",
        )
        self.assertEqual(
            thread_author_notification.title,
            "댓글작성자 님의 댓글에 댓글이 달렸어요.",
        )
        self.assertEqual(
            direct_target_notification.data,
            {
                "lecture_id": str(self.lecture.id),
                "comment_id": str(response.data["id"]),
                "parent_comment_id": str(parent.id),
                "reply_to_comment_id": str(direct_target.id),
            },
        )
        self.assertEqual(thread_author_notification.data, direct_target_notification.data)
        self.assertEqual(send_push.call_count, 2)

    def test_reply_target_name_falls_back_after_target_deletion_and_for_legacy_reply(self):
        parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.commenter,
            author_role="student",
            content="원댓글",
        )
        direct_target = Comment.objects.create(
            lecture=self.lecture,
            author=self.replier,
            author_role="student",
            parent=parent,
            content="직접 대상",
        )
        reply = Comment.objects.create(
            lecture=self.lecture,
            author=self.owner,
            author_role="instructor",
            parent=parent,
            reply_to=direct_target,
            content="직접 답글",
        )
        legacy_reply = Comment.objects.create(
            lecture=self.lecture,
            author=self.owner,
            author_role="instructor",
            parent=parent,
            content="구버전 답글",
        )

        direct_target.delete()
        response = self.client.get(self._comment_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        replies = response.data["results"][0]["replies"]
        reply_data = next(item for item in replies if item["id"] == reply.id)
        legacy_data = next(item for item in replies if item["id"] == legacy_reply.id)
        self.assertEqual(reply_data["referenced_person_name"], "답글작성자")
        self.assertEqual(legacy_data["referenced_person_name"], "댓글작성자")

    def test_reply_to_must_belong_to_the_same_root_comment_group(self):
        parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.commenter,
            author_role="student",
            content="첫 원댓글",
        )
        other_parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.replier,
            author_role="student",
            content="다른 원댓글",
        )

        response = self._post_comment(
            self.owner,
            {
                "content": "잘못된 직접 대상",
                "parent": parent.id,
                "reply_to": other_parent.id,
                "author_role": "instructor",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reply_to", response.data)
        self.assertFalse(Comment.objects.filter(content="잘못된 직접 대상").exists())

    def test_reply_to_must_belong_to_the_same_lecture(self):
        parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.commenter,
            author_role="student",
            content="현재 강의 원댓글",
        )
        other_lecture = Lecture.objects.create(
            instructor=self.instructor,
            title="다른 강의",
            price=0,
        )
        other_lecture_comment = Comment.objects.create(
            lecture=other_lecture,
            author=self.replier,
            author_role="student",
            content="다른 강의 댓글",
        )

        response = self._post_comment(
            self.owner,
            {
                "content": "다른 강의 직접 대상",
                "parent": parent.id,
                "reply_to": other_lecture_comment.id,
                "author_role": "instructor",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reply_to", response.data)
        self.assertFalse(Comment.objects.filter(content="다른 강의 직접 대상").exists())

    @patch("config.apps.notification.fcm.send_push_to_user")
    def test_reply_to_self_skips_self_but_notifies_thread_author(self, send_push):
        parent = Comment.objects.create(
            lecture=self.lecture,
            author=self.commenter,
            author_role="student",
            content="원댓글",
        )
        own_reply = Comment.objects.create(
            lecture=self.lecture,
            author=self.replier,
            author_role="student",
            parent=parent,
            content="내 답글",
        )

        response = self._post_comment(
            self.replier,
            {
                "content": "내 답글에 답글",
                "parent": parent.id,
                "reply_to": own_reply.id,
                "author_role": "student",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get()
        self.assertEqual(notification.user_id, self.commenter.id)
        self.assertEqual(notification.role, "student")
        self.assertEqual(notification.title, "댓글작성자 님의 댓글에 댓글이 달렸어요.")
        send_push.assert_called_once()

    @patch("config.apps.notification.fcm.send_push_to_user")
    def test_self_comment_does_not_create_notification(self, send_push):
        response = self._post_comment(
            self.owner,
            {"content": "내 영상 댓글", "author_role": "instructor"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Notification.objects.exists())
        send_push.assert_not_called()

    def test_explicit_role_requires_matching_profile(self):
        response = self._post_comment(
            self.commenter,
            {"content": "잘못된 역할", "author_role": "instructor"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("author_role", response.data)
        self.assertFalse(Comment.objects.filter(content="잘못된 역할").exists())

    def test_missing_role_uses_instructor_for_dual_profile_user(self):
        dual_user = User.objects.create_user(
            username="dual-commenter",
            user_name="겸업작성자",
        )
        Student.objects.create(user=dual_user)
        Instructor.objects.create(user=dual_user, university="Dual Univ")

        response = self._post_comment(dual_user, {"content": "구버전 댓글"})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["author_role"], "instructor")
