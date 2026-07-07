from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from config.apps.accounts.models import User, Student, Instructor
from config.apps.pending.models import PendingInstructor
from rest_framework.authtoken.models import Token


class PendingGetAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users
        self.student_user = User.objects.create_user(username="student", user_name="student", password="password123")
        self.instructor_user = User.objects.create_user(username="instructor", user_name="instructor", password="password123")

        # Create profiles
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(user=self.instructor_user, university="Test University")

    def test_unauthenticated_request_returns_401(self):
        """Unauthenticated requests should return 401 Unauthorized."""
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_request_returns_403(self):
        """Students who are not instructors should receive 403 Forbidden."""
        token, _ = Token.objects.get_or_create(user=self.student_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {"error": "강사 프로필이 존재하지 않습니다."})

    def test_instructor_without_pending_returns_false_and_none(self):
        """Instructors without a PendingInstructor entry should receive exists: false."""
        token, _ = Token.objects.get_or_create(user=self.instructor_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"exists": False, "status": None})

    def test_instructor_with_pending_status(self):
        """Instructors with a PendingInstructor entry in PENDING status should receive exists: true, status: PENDING."""
        PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.PENDING
        )
        token, _ = Token.objects.get_or_create(user=self.instructor_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"exists": True, "status": "PENDING"})

    def test_instructor_with_verified_status(self):
        """Instructors with a PendingInstructor entry in VERIFIED status should receive exists: true, status: VERIFIED."""
        PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.VERIFIED
        )
        token, _ = Token.objects.get_or_create(user=self.instructor_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"exists": True, "status": "VERIFIED"})

    def test_instructor_with_suspended_status(self):
        """Instructors with a PendingInstructor entry in SUSPENDED status should receive exists: true, status: SUSPENDED, and rejection_reason."""
        PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.SUSPENDED,
            rejection_reason="서류 화질이 불분명함."
        )
        token, _ = Token.objects.get_or_create(user=self.instructor_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {
            "exists": True,
            "status": "SUSPENDED",
            "rejection_reason": "서류 화질이 불분명함."
        })

    def test_instructor_post_with_suspended_status_returns_rejection_reason(self):
        """이미 SUSPENDED 상태인데 다시 POST 요청을 보내는 경우 rejection_reason이 에러 응답에 포함되어야 함."""
        PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.SUSPENDED,
            rejection_reason="인증 서류 누락."
        )
        token, _ = Token.objects.get_or_create(user=self.instructor_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        
        response = self.client.post("/pending/", data={"pending_file": []})  # data content doesn't matter since it blocks at already exists
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {
            "error": "이미 인증 신청 내역이 존재합니다.",
            "status": "SUSPENDED",
            "rejection_reason": "인증 서류 누락."
        })

