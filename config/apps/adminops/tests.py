from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import AdminActionLog

User = get_user_model()

PASSWORD = "Passw0rd!123"


class AdminAuthTests(APITestCase):
    login_url = "/admin-api/v1/auth/login/"
    me_url = "/admin-api/v1/auth/me/"

    def _make_user(self, email, *, superuser):
        user = User.objects.create_user(
            username=email, email=email, user_name=email, password=PASSWORD
        )
        if superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
        return user

    def test_superuser_login_returns_token_and_user(self):
        self._make_user("super@example.com", superuser=True)
        res = self.client.post(
            self.login_url,
            {"email": "super@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.data)
        self.assertEqual(res.data["user"]["email"], "super@example.com")
        self.assertTrue(res.data["user"]["is_superuser"])

    def test_non_superuser_login_is_forbidden(self):
        self._make_user("plain@example.com", superuser=False)
        res = self.client.post(
            self.login_url,
            {"email": "plain@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Token.objects.filter(user__email="plain@example.com").exists())

    def test_wrong_password_returns_401(self):
        self._make_user("super2@example.com", superuser=True)
        res = self.client.post(
            self.login_url,
            {"email": "super2@example.com", "password": "nope"},
            format="json",
        )
        self.assertEqual(res.status_code, 401)

    def test_login_validates_input(self):
        res = self.client.post(self.login_url, {"email": "not-an-email"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_me_requires_superuser_token(self):
        # 익명 접근 거부
        self.assertEqual(self.client.get(self.me_url).status_code, 401)

        # 일반 사용자 토큰 거부
        plain = self._make_user("plain2@example.com", superuser=False)
        plain_token = Token.objects.create(user=plain)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {plain_token.key}")
        self.assertEqual(self.client.get(self.me_url).status_code, 403)

        # 슈퍼관리자 토큰 허용
        su = self._make_user("super3@example.com", superuser=True)
        su_token = Token.objects.create(user=su)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {su_token.key}")
        res = self.client.get(self.me_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["email"], "super3@example.com")


class AdminActionLogTests(APITestCase):
    def test_log_is_append_only(self):
        admin = User.objects.create_user(
            username="log@example.com",
            email="log@example.com",
            user_name="log@example.com",
            password=PASSWORD,
        )
        log = AdminActionLog.record(
            admin=admin,
            action="settlement.complete",
            target_type="SettlementRecord",
            target_id=42,
            reason="지급 완료",
            metadata={"amount": 10000},
        )
        self.assertEqual(log.admin_email, "log@example.com")
        self.assertEqual(log.target_id, "42")

        log.reason = "변경 시도"
        with self.assertRaises(ValueError):
            log.save()
