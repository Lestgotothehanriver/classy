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
        """Instructors with a PendingInstructor entry in SUSPENDED status should receive exists: true, status: SUSPENDED."""
        PendingInstructor.objects.create(
            instructor_profile=self.instructor,
            status=PendingInstructor.Status.SUSPENDED
        )
        token, _ = Token.objects.get_or_create(user=self.instructor_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/pending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"exists": True, "status": "SUSPENDED"})
