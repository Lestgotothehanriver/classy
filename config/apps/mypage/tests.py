import json
import logging
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.utils import timezone

from config.apps.accounts.models import User, Student, Instructor, Subject
from config.apps.cash.models import InstructorMonthlyRank, LectureRentalHistory, SettlementRecord
from config.apps.lecture.models import Lecture

logger = logging.getLogger(__name__)

class MypageAPIViewSetTests(APITestCase):

    def setUp(self):
        # Create users
        self.student_user = User.objects.create_user(
            username="student_login", password="password", region="서울 강남구", user_name="student_user"
        )
        self.student = Student.objects.create(user=self.student_user)

        self.instructor_user = User.objects.create_user(
            username="instructor_login", password="password", region="서울 송파구", user_name="instructor_user"
        )
        self.instructor = Instructor.objects.create(user=self.instructor_user, university="서울대")

        # Create subjects 
        subj = Subject.objects.create(number=1)
        self.instructor.subjects.add(subj)

        now = timezone.now()
        
        self.lecture = Lecture.objects.create(
            title="Test Mypage Lecture",
            instructor=self.instructor,
            price=1500,
            is_delete=False
        )

        LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.student_user,
            purchased_cash=1500,
            remaining_cash=0,
            is_canceled=False,
            is_settled=False
        )
        history = LectureRentalHistory.objects.first()
        history.created_at = now
        history.save()

    def test_student_rented_lectures(self):
        url = reverse('student-rented-lectures')
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_student_liked_lectures(self):
        self.lecture.likes.add(self.student)
        url = reverse('student-liked-lectures')
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_instructor_uploaded_lectures(self):
        url = reverse('instructor-uploaded-lectures')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_instructor_settlement_info(self):
        url = reverse('instructor-settlement-info')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['settleable_revenue'], 1500)

    def test_instructor_request_settlement(self):
        url = reverse('instructor-request-settlement')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount'], 1500)
        self.assertTrue(SettlementRecord.objects.filter(instructor=self.instructor).exists())
