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
            data = {
                'email': f'fixture{index}@example.com',
                'password': 'TestPassword987!',
                'phone': '01000000930',
                'user_name': f'fixture{index}',
                'first_name': '테스트',
                'sex': '남성',
                'birth_date': '2000-01-01',
                'region': '서울 강남구',
                'agreed_age': True,
                'agreed_terms': True,
                'agreed_privacy': True,
            }
            if serializer_class is StudentSignupSerializer:
                data['studentsubject'] = [1]
            else:
                data.update({
                    'university': 'App Review demo',
                    'department': '컴퓨터공학과',
                    'student_number': '2020',
                    'instruction': '앱 심사용 선생님 소개입니다.',
                    'instructorsubject': '[1]',
                })
            serializer = serializer_class(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            user = serializer.save()
            self.assertEqual(user.iap_environment, 'SANDBOX')
            user.phone = None
            user.save(update_fields=['phone'])

    def test_normal_signup_wallet_stays_production(self):
        serializer = StudentSignupSerializer(data={
            'email': 'normal@example.com',
            'password': 'TestPassword987!',
            'user_name': 'normal',
            'first_name': '일반',
            'phone': '01099998888',
            'sex': '남성',
            'birth_date': '2000-01-01',
            'region': '서울 강남구',
            'studentsubject': [1],
            'agreed_age': True,
            'agreed_terms': True,
            'agreed_privacy': True,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save().iap_environment, 'PRODUCTION')

    def test_signup_requires_explicit_required_policy_consents(self):
        base_data = {
            'email': 'consent@example.com',
            'password': 'TestPassword987!',
            'user_name': 'consent',
            'first_name': '동의',
            'phone': '01099998888',
            'sex': '남성',
            'birth_date': '2000-01-01',
            'region': '서울 강남구',
            'studentsubject': [1],
            'agreed_age': True,
        }

        missing_terms = StudentSignupSerializer(
            data={**base_data, 'agreed_privacy': True},
        )
        missing_age_data = dict(base_data)
        missing_age_data.pop('agreed_age')
        missing_age = StudentSignupSerializer(
            data={
                **missing_age_data,
                'agreed_terms': True,
                'agreed_privacy': True,
            },
        )
        declined_privacy = StudentSignupSerializer(
            data={**base_data, 'agreed_terms': True, 'agreed_privacy': False},
        )

        self.assertFalse(missing_terms.is_valid())
        self.assertIn('agreed_terms', missing_terms.errors)
        self.assertFalse(missing_age.is_valid())
        self.assertIn('agreed_age', missing_age.errors)
        self.assertFalse(declined_privacy.is_valid())
        self.assertIn('agreed_privacy', declined_privacy.errors)

    def test_signup_limits_selected_subjects_to_nine(self):
        serializer = StudentSignupSerializer(
            data={
                'email': 'subjects@example.com',
                'password': 'TestPassword987!',
                'user_name': 'subjects',
                'first_name': '과목',
                'phone': '01099998888',
                'sex': '남성',
                'birth_date': '2000-01-01',
                'region': '서울 강남구',
                'agreed_age': True,
                'agreed_terms': True,
                'agreed_privacy': True,
                'studentsubject': list(range(1, 11)),
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('studentsubject', serializer.errors)

    def test_signup_rejects_underage_and_weak_password(self):
        base_data = {
            'email': 'validation@example.com',
            'password': 'TestPassword987!',
            'user_name': 'validation',
            'first_name': '검증',
            'phone': '01099998888',
            'sex': '남성',
            'birth_date': '2000-01-01',
            'region': '서울 강남구',
            'studentsubject': [1],
            'agreed_age': True,
            'agreed_terms': True,
            'agreed_privacy': True,
        }
        underage = StudentSignupSerializer(
            data={**base_data, 'birth_date': '2020-01-01'},
        )
        weak_password = StudentSignupSerializer(
            data={**base_data, 'password': 'password123'},
        )

        self.assertFalse(underage.is_valid())
        self.assertIn('birth_date', underage.errors)
        self.assertFalse(weak_password.is_valid())
        self.assertIn('password', weak_password.errors)

    def test_teacher_signup_limits_subjects_to_three(self):
        serializer = InstructorSignupSerializer(
            data={
                'email': 'teacher-subjects@example.com',
                'password': 'TestPassword987!',
                'user_name': 'teacher',
                'first_name': '선생',
                'phone': '01099998888',
                'sex': '남성',
                'birth_date': '2000-01-01',
                'region': '서울 강남구',
                'university': '테스트대학교',
                'department': '컴퓨터공학과',
                'student_number': '2020',
                'instruction': '성실하게 수업합니다.',
                'instructorsubject': '[1, 2, 3, 4]',
                'agreed_age': True,
                'agreed_terms': True,
                'agreed_privacy': True,
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('instructorsubject', serializer.errors)

    @override_settings(APP_REVIEW_SIGNUP_CODE='')
    @patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
    @patch('config.apps.accounts.views.send_auth_sms', return_value=True)
    def test_fixture_disabled_without_configured_code(self, sms, throttle):
        self.client.post('/accounts/send-auth-sms/', {'phone_number': '01000000930'})
        sms.assert_called_once()
