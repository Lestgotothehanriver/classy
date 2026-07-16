from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from config.apps.accounts.models import Instructor
from config.apps.cash.models import LectureRentalHistory
from config.apps.lecture.models import Comment, Lecture


User = get_user_model()


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
        self.assertEqual(len(response.data), 1)

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
