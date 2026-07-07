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


from unittest.mock import patch

class PhoneVerificationTests(APITestCase):
    def setUp(self):
        self.send_url = reverse("accounts:send-auth-sms")
        self.verify_url = reverse("accounts:verify-auth-sms")
        self.phone = "01099998888"
        self.patcher = patch('config.apps.accounts.views.send_auth_sms', return_value=True)
        self.mock_send_sms = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_send_auth_sms_success(self):
        """전화번호가 제공되면 인증번호가 SMS로 발송(모킹/로그)되고 200 응답과 인증코드를 받아야 합니다."""
        response = self.client.post(self.send_url, {"phone_number": self.phone})
        self.assertEqual(response.status_code, 200)
        self.assertIn("code", response.data)
        
        from config.apps.accounts.models import PhoneVerification
        verification = PhoneVerification.objects.filter(phone=self.phone).first()
        self.assertIsNotNone(verification)
        self.assertEqual(verification.code, response.data["code"])
        self.assertFalse(verification.is_verified)
        self.assertIsNone(verification.user)  # Unregistered user case

    def test_send_auth_sms_failure(self):
        """SMS 발송에 실패하면 400 에러를 반환해야 합니다."""
        self.mock_send_sms.return_value = False
        response = self.client.post(self.send_url, {"phone_number": self.phone})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_send_auth_sms_missing_phone(self):
        """전화번호가 누락되면 400 에러를 반환해야 합니다."""
        response = self.client.post(self.send_url, {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_verify_auth_sms_success(self):
        """올바른 인증코드를 입력하면 인증이 완료되고 200 응답을 받아야 합니다."""
        # 1. Send code
        send_response = self.client.post(self.send_url, {"phone_number": self.phone})
        code = send_response.data["code"]

        # 2. Verify code
        verify_response = self.client.post(self.verify_url, {
            "phone_number": self.phone,
            "code": code
        })
        self.assertEqual(verify_response.status_code, 200)
        
        from config.apps.accounts.models import PhoneVerification
        verification = PhoneVerification.objects.filter(phone=self.phone).first()
        self.assertTrue(verification.is_verified)

    def test_verify_auth_sms_invalid_code(self):
        """틀린 인증코드를 입력하면 400 에러를 반환해야 합니다."""
        # 1. Send code
        self.client.post(self.send_url, {"phone_number": self.phone})

        # 2. Verify with wrong code
        verify_response = self.client.post(self.verify_url, {
            "phone_number": self.phone,
            "code": "000000"
        })
        self.assertEqual(verify_response.status_code, 400)
        self.assertIn("error", verify_response.data)

    def test_verify_auth_sms_missing_fields(self):
        """필수 입력값이 누락되면 400 에러를 반환해야 합니다."""
        # missing code
        response = self.client.post(self.verify_url, {"phone_number": self.phone})
        self.assertEqual(response.status_code, 400)

        # missing phone_number
        response = self.client.post(self.verify_url, {"code": "123456"})
        self.assertEqual(response.status_code, 400)
