"""알림 API의 역할별 읽음 처리 회귀 테스트."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Notification


class NotificationReadAllTests(APITestCase):
    """역할 필터가 다른 역할의 읽지 않은 알림을 건드리지 않는지 검증한다."""

    def setUp(self):
        """학생·강사 역할 알림을 같은 사용자에게 생성한다."""
        self.user = get_user_model().objects.create_user(
            username="notification@example.com",
            email="notification@example.com",
            user_name="notification_user",
            password="pass1234",
        )
        self.client.force_authenticate(user=self.user)
        self.student_notification = Notification.objects.create(
            user=self.user,
            type="message",
            role="student",
            title="학생 알림",
            body="학생 역할 알림",
        )
        self.instructor_notification = Notification.objects.create(
            user=self.user,
            type="message",
            role="instructor",
            title="강사 알림",
            body="강사 역할 알림",
        )

    def test_read_all_marks_only_requested_role(self):
        """`role` 쿼리로 지정한 역할의 알림만 읽음 처리한다."""
        response = self.client.patch("/notification/read-all/?role=student")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        self.student_notification.refresh_from_db()
        self.instructor_notification.refresh_from_db()
        self.assertTrue(self.student_notification.is_read)
        self.assertFalse(self.instructor_notification.is_read)
