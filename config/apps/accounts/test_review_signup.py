from unittest.mock import patch
from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import PhoneVerification
from .serializers import StudentSignupSerializer, InstructorSignupSerializer


@override_settings(APP_REVIEW_SIGNUP_PHONES=('01000000930',), APP_REVIEW_SIGNUP_CODE='930614')
class ReviewSignupTests(APITestCase):
    @patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
    @patch('config.apps.accounts.views.send_auth_sms', return_value=True)
    def test_fixture_verifies_without_sms_and_rejects_wrong_code(self, sms, throttle):
        sent = self.client.post('/accounts/send-auth-sms/', {'phone_number': '01000000930'})
        self.assertEqual(sent.status_code, 200)
        sms.assert_not_called()
        wrong = self.client.post('/accounts/verify-auth-sms/', {'phone_number': '01000000930', 'code': '000000'})
        self.assertEqual(wrong.status_code, 400)
        verified = self.client.post('/accounts/verify-auth-sms/', {'phone_number': '01000000930', 'code': '930614'})
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(PhoneVerification.objects.get(phone='01000000930').is_verified)

    @patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
    @patch('config.apps.accounts.views.send_auth_sms', return_value=True)
    def test_customer_number_still_sends_sms(self, sms, throttle):
        result = self.client.post('/accounts/send-auth-sms/', {'phone_number': '01099998888'})
        self.assertEqual(result.status_code, 200)
        sms.assert_called_once()

    @patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
    @patch('config.apps.accounts.views.send_auth_sms', return_value=True)
    def test_fixture_does_not_apply_to_existing_production_identity(self, sms, throttle):
        get_user_model().objects.create_user(username='real', email='real@example.com', user_name='real', phone='010-0000-0930')
        self.client.post('/accounts/send-auth-sms/', {'phone_number': '01000000930'})
        sms.assert_called_once()

    def test_student_and_instructor_fixture_wallets_are_sandbox(self):
        for index, serializer_class in enumerate((StudentSignupSerializer, InstructorSignupSerializer)):
            data = {'email': f'fixture{index}@example.com', 'password': 'TestPassword987!', 'phone': '01000000930', 'user_name': f'fixture{index}', 'university': 'App Review demo'}
            serializer = serializer_class(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            user = serializer.save()
            self.assertEqual(user.iap_environment, 'SANDBOX')
            user.phone = None
            user.save(update_fields=['phone'])

    def test_normal_signup_wallet_stays_production(self):
        serializer = StudentSignupSerializer(data={'email': 'normal@example.com', 'password': 'TestPassword987!', 'user_name': 'normal', 'phone': '01099998888'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save().iap_environment, 'PRODUCTION')

    @override_settings(APP_REVIEW_SIGNUP_CODE='')
    @patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
    @patch('config.apps.accounts.views.send_auth_sms', return_value=True)
    def test_fixture_disabled_without_configured_code(self, sms, throttle):
        self.client.post('/accounts/send-auth-sms/', {'phone_number': '01000000930'})
        sms.assert_called_once()
