from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from unittest.mock import patch
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.settings import api_settings

User = get_user_model()

class RateLimitThrottlingTests(APITestCase):
    def setUp(self):
        # Clear cache between tests to avoid pollution
        cache.clear()
        
        # Manually override SimpleRateThrottle.THROTTLE_RATES to make testing rates low
        self.original_throttle_rates = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = {
            'safe_method': '2/min',
            'unsafe_method': '2/min',
            'login': '2/min',
            'sms': '2/min',
            'purchase': '2/min',
        }
        
        self.user = User.objects.create_user(
            username="throttle_test@example.com",
            email="throttle_test@example.com",
            password="testpassword123",
            user_name="throttler"
        )
        # Mock external dependencies
        self.patcher_sms = patch('config.apps.accounts.views.send_auth_sms', return_value=True)
        self.mock_send_sms = self.patcher_sms.start()
        
    def tearDown(self):
        self.patcher_sms.stop()
        # Restore original throttle rates
        SimpleRateThrottle.THROTTLE_RATES = self.original_throttle_rates

    def test_safe_method_rate_limiting(self):
        """GET (safe method) API calls should be throttled after exceeding the rate (2/min)."""
        url = reverse("accounts:check-email")
        
        response = self.client.get(url, {"email": "test1@example.com"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(url, {"email": "test2@example.com"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(url, {"email": "test3@example.com"})
        self.assertEqual(response.status_code, 429)

    def test_unsafe_method_rate_limiting(self):
        """POST (unsafe method) API calls should be throttled after exceeding the rate (2/min)."""
        url = reverse("accounts:check-email")
        
        response = self.client.post(url, {"email": "test1@example.com"})
        self.assertEqual(response.status_code, 405)

        response = self.client.post(url, {"email": "test2@example.com"})
        self.assertEqual(response.status_code, 405)

        response = self.client.post(url, {"email": "test3@example.com"})
        self.assertEqual(response.status_code, 429)

    def test_login_rate_limiting(self):
        """Login API calls should be throttled by LoginRateThrottle after exceeding the rate (2/min)."""
        url = reverse("accounts:login")
        
        response = self.client.post(url, {"email": "throttle_test@example.com", "password": "wrongpassword"}, format='json')
        self.assertEqual(response.status_code, 400)

        response = self.client.post(url, {"email": "throttle_test@example.com", "password": "wrongpassword"}, format='json')
        self.assertEqual(response.status_code, 400)

        response = self.client.post(url, {"email": "throttle_test@example.com", "password": "wrongpassword"}, format='json')
        self.assertEqual(response.status_code, 429)

    def test_sms_rate_limiting(self):
        """SMS send API calls should be throttled by SMSRateThrottle after exceeding the rate (2/min)."""
        url = reverse("accounts:send-auth-sms")
        phone = "01011112222"
        
        response = self.client.post(url, {"phone_number": phone}, format='json')
        self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {"phone_number": phone}, format='json')
        self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {"phone_number": phone}, format='json')
        self.assertEqual(response.status_code, 429)

    @patch('config.apps.cash.views.verify_apple_receipt')
    def test_purchase_rate_limiting(self, mock_verify):
        """Purchase API calls should be throttled by PurchaseRateThrottle after exceeding the rate (2/min)."""
        mock_verify.side_effect = [
            (True, 'apple_tx_001', ''),
            (True, 'apple_tx_002', ''),
            (True, 'apple_tx_003', ''),
        ]
        url = reverse("cash:purchase")
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post(url, {
            'platform': 'apple',
            'receipt_data': 'valid_receipt_base64',
            'product_id': 'cash_1000',
        }, format='json')
        self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {
            'platform': 'apple',
            'receipt_data': 'valid_receipt_base64',
            'product_id': 'cash_1000',
        }, format='json')
        self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {
            'platform': 'apple',
            'receipt_data': 'valid_receipt_base64',
            'product_id': 'cash_1000',
        }, format='json')
        self.assertEqual(response.status_code, 429)
