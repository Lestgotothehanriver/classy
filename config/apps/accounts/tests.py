from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
User = get_user_model()


class UserProfileEditPrefillTests(APITestCase):
    """강사 프로필 수정 폼에 필요한 GET /accounts/me/ 응답을 검증한다."""

    def test_instructor_profile_get_contains_editable_fields(self):
        from config.apps.accounts.models import Instructor, Subject

        user = User.objects.create_user(
            username="teacher@example.com",
            email="teacher@example.com",
            user_name="teacher",
            password="pass1234",
            sex="여성",
            birth_date="1998-03-02",
            region="서울 강남구",
        )
        instructor = Instructor.objects.create(
            user=user,
            university="테스트대학교",
            department="수학과",
            instruction="꼼꼼하게 지도합니다.",
            student_number="2018",
        )
        subject = Subject.objects.create(number=1)
        instructor.subjects.add(subject)
        self.client.force_authenticate(user=user)

        response = self.client.get(reverse("accounts:user-profile"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "instructor")
        self.assertEqual(response.data["sex"], "여성")
        self.assertEqual(response.data["birth_date"], "1998-03-02")
        self.assertEqual(response.data["region"], "서울 강남구")
        self.assertEqual(response.data["instruction"], "꼼꼼하게 지도합니다.")
        self.assertEqual(response.data["subjects"], [str(subject)])

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
        
        # Mock SMS sending
        self.patcher = patch('config.apps.accounts.views.send_auth_sms', return_value=True)
        self.mock_send_sms = self.patcher.start()
        
        # Mock Throttling to prevent 429 errors in tests
        self.throttle_patcher = patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
        self.mock_throttle = self.throttle_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.throttle_patcher.stop()

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


from config.apps.accounts.models import Student, Instructor, Subject
from config.apps.pending.models import PendingInstructor

class ProfileCheckAPIViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("accounts:profile-check")
        self.student_email = "student@example.com"
        self.student_user = User.objects.create_user(
            username=self.student_email,
            email=self.student_email,
            password="securepassword123",
            user_name="student_user",
            phone="01011112222"
        )
        self.student_profile = Student.objects.create(user=self.student_user)

        self.instructor_email = "instructor@example.com"
        self.instructor_user = User.objects.create_user(
            username=self.instructor_email,
            email=self.instructor_email,
            password="securepassword123",
            user_name="instructor_user",
            phone="01033334444"
        )
        self.instructor_profile = Instructor.objects.create(
            user=self.instructor_user,
            university="Test University",
            department="Test Department"
        )
        self.pending_info = PendingInstructor.objects.create(
            instructor_profile=self.instructor_profile,
            status=PendingInstructor.Status.PENDING
        )

    def test_profile_check_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_profile_check_student_only(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_id"], self.student_user.id)
        self.assertEqual(response.data["email"], self.student_email)
        self.assertEqual(len(response.data["available_roles"]), 1)
        self.assertEqual(response.data["available_roles"][0]["role"], "student")
        self.assertEqual(response.data["available_roles"][0]["status"], "VERIFIED")
        self.assertIsNone(response.data["available_roles"][0]["last_login"])

        # Second hit should have last_login
        response2 = self.client.get(self.url)
        self.assertIsNotNone(response2.data["available_roles"][0]["last_login"])

    def test_profile_check_instructor_only(self):
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_id"], self.instructor_user.id)
        self.assertEqual(response.data["email"], self.instructor_email)
        self.assertEqual(len(response.data["available_roles"]), 1)
        self.assertEqual(response.data["available_roles"][0]["role"], "instructor")
        self.assertEqual(response.data["available_roles"][0]["status"], "PENDING")
        self.assertIsNone(response.data["available_roles"][0]["last_login"])

        # Second hit should have last_login
        response2 = self.client.get(self.url)
        self.assertIsNotNone(response2.data["available_roles"][0]["last_login"])

    def test_profile_check_both_roles(self):
        # Add instructor profile to student user
        instructor_profile = Instructor.objects.create(
            user=self.student_user,
            university="Test University 2"
        )
        PendingInstructor.objects.create(
            instructor_profile=instructor_profile,
            status=PendingInstructor.Status.VERIFIED
        )
        
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["available_roles"]), 2)
        
        roles = {r["role"]: r for r in response.data["available_roles"]}
        self.assertIn("student", roles)
        self.assertIn("instructor", roles)
        self.assertEqual(roles["student"]["status"], "VERIFIED")
        self.assertEqual(roles["instructor"]["status"], "VERIFIED")


class RoleAddAPIViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("accounts:role-add")
        self.student_email = "student2@example.com"
        self.student_user = User.objects.create_user(
            username=self.student_email,
            email=self.student_email,
            password="securepassword123",
            user_name="student_user2",
            phone="01055556666"
        )
        self.student_profile = Student.objects.create(user=self.student_user)

        self.instructor_email = "instructor2@example.com"
        self.instructor_user = User.objects.create_user(
            username=self.instructor_email,
            email=self.instructor_email,
            password="securepassword123",
            user_name="instructor_user2",
            phone="01077778888"
        )
        self.instructor_profile = Instructor.objects.create(
            user=self.instructor_user,
            university="Test University",
            department="Test Department"
        )
        PendingInstructor.objects.create(
            instructor_profile=self.instructor_profile,
            status=PendingInstructor.Status.PENDING
        )

    def test_role_add_unauthenticated(self):
        response = self.client.post(f"{self.url}?role=student")
        self.assertEqual(response.status_code, 401)

    def test_role_add_missing_role_parameter(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_role_add_invalid_role_parameter(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(f"{self.url}?role=invalid")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_role_add_existing_student_role_fails(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(f"{self.url}?role=student")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "이미 학생 프로필이 존재합니다.")

    def test_role_add_existing_instructor_role_fails(self):
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.post(f"{self.url}?role=instructor")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "이미 강사 프로필이 존재합니다.")

    def test_role_add_student_role_to_instructor_success(self):
        self.client.force_authenticate(user=self.instructor_user)
        # Create subjects for testing
        subject1, _ = Subject.objects.get_or_create(number=1)
        subject2, _ = Subject.objects.get_or_create(number=2)

        data = {
            "studentsubject": [subject1.number, subject2.number]
        }
        response = self.client.post(f"{self.url}?role=student", data, format="json")
        self.assertEqual(response.status_code, 201)
        
        # Verify student profile exists
        self.assertTrue(Student.objects.filter(user=self.instructor_user).exists())
        student_profile = Student.objects.get(user=self.instructor_user)
        self.assertEqual(student_profile.subjects.count(), 2)
        
        # Verify response structure
        self.assertEqual(len(response.data["available_roles"]), 2)
        roles = {r["role"]: r for r in response.data["available_roles"]}
        self.assertIn("student", roles)
        self.assertIn("instructor", roles)

    def test_role_add_instructor_role_to_student_success(self):
        self.client.force_authenticate(user=self.student_user)
        # Create subjects for testing
        subject3, _ = Subject.objects.get_or_create(number=3)

        data = {
            "university": "SNU",
            "department": "CS",
            "instruction": "Hello, I am a new instructor",
            "student_number": "2020-12345",
            "instructorsubject": f"[{subject3.number}]"
        }
        response = self.client.post(f"{self.url}?role=instructor", data, format="json")
        self.assertEqual(response.status_code, 201)

        # Verify instructor profile and PendingInstructor exists
        self.assertTrue(Instructor.objects.filter(user=self.student_user).exists())
        instructor_profile = Instructor.objects.get(user=self.student_user)
        self.assertEqual(instructor_profile.university, "SNU")
        self.assertEqual(instructor_profile.department, "CS")
        self.assertEqual(instructor_profile.instruction, "Hello, I am a new instructor")
        self.assertEqual(instructor_profile.student_number, "2020-12345")
        self.assertEqual(instructor_profile.subjects.count(), 1)
        
        self.assertTrue(PendingInstructor.objects.filter(instructor_profile=instructor_profile).exists())
        pending = PendingInstructor.objects.get(instructor_profile=instructor_profile)
        self.assertEqual(pending.status, PendingInstructor.Status.PENDING)
