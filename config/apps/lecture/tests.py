from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from config.apps.accounts.models import User, Student, Instructor
from config.apps.lecture.models import Lecture

class LectureThumbnailTests(APITestCase):
    def setUp(self):
        # Create users
        self.student_user = User.objects.create_user(
            username="student_test@example.com", password="password", region="서울 강남구", user_name="student_test"
        )
        self.student = Student.objects.create(user=self.student_user)
        
        self.instructor_user = User.objects.create_user(
            username="instructor_test@example.com", password="password", region="서울 송파구", user_name="instructor_test"
        )
        self.instructor = Instructor.objects.create(user=self.instructor_user, university="서울대")

        # Create dummy image for thumbnail
        dummy_gif = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04'
            b'\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02'
            b'\x02\x4c\x01\x00\x3b'
        )
        self.thumbnail_file = SimpleUploadedFile("thumb.gif", dummy_gif, content_type="image/gif")

        # Create a lecture
        self.lecture = Lecture.objects.create(
            title="테스트용 강의",
            instructor=self.instructor,
            price=5000,
            thumbnail=self.thumbnail_file,
            is_active=True,
            is_delete=False
        )

        self.client.force_authenticate(user=self.student_user)

    def test_lecture_list_contains_thumbnail_and_thumbnail_url(self):
        url = reverse("lecture-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        results = response.data.get("results", [])
        self.assertTrue(len(results) > 0)
        
        # Check thumbnail and thumbnail_url keys
        lecture_data = results[0]
        self.assertIn("thumbnail", lecture_data)
        self.assertIn("thumbnail_url", lecture_data)
        self.assertIsNotNone(lecture_data["thumbnail"])
        self.assertIsNotNone(lecture_data["thumbnail_url"])
        self.assertTrue(lecture_data["thumbnail"].startswith("http://"))
        self.assertTrue(lecture_data["thumbnail_url"].startswith("http://"))

    def test_lecture_detail_contains_thumbnail_and_thumbnail_url(self):
        url = reverse("lecture-detail", args=[self.lecture.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        lecture_info = response.data.get("lecture_info")
        self.assertIsNotNone(lecture_info)
        self.assertIn("thumbnail", lecture_info)
        self.assertIn("thumbnail_url", lecture_info)
        self.assertIsNotNone(lecture_info["thumbnail"])
        self.assertIsNotNone(lecture_info["thumbnail_url"])
        self.assertTrue(lecture_info["thumbnail"].startswith("http://"))
        self.assertTrue(lecture_info["thumbnail_url"].startswith("http://"))
