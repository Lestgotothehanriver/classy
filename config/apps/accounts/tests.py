from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

User = get_user_model()

class CheckEmailAPIViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("accounts:check-email")
        self.user_email = "testuser@example.com"
        self.user = User.objects.create_user(
            username=self.user_email,
            email=self.user_email,
            password="securepassword123",
            user_name="testuser"
        )

    def test_check_email_missing_parameter(self):
        """이메일 쿼리 매개변수가 없는 경우 400 에러를 반환해야 합니다."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "email query parameter required")

    def test_check_email_available(self):
        """존재하지 않는 이메일인 경우 available: True여야 합니다."""
        response = self.client.get(self.url, {"email": "newuser@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_check_email_taken(self):
        """이미 존재하는 이메일인 경우 available: False여야 합니다."""
        response = self.client.get(self.url, {"email": self.user_email})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])

    def test_check_email_taken_case_insensitive(self):
        """이메일 중복 검사는 대소문자를 구분하지 않아야 합니다."""
        response = self.client.get(self.url, {"email": "TESTUSER@EXAMPLE.COM"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])

    def test_check_email_exclude_current_user(self):
        """현재 로그인된 사용자의 이메일은 중복 검사에서 제외되어 available: True여야 합니다."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"email": self.user_email})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
