from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.utils import timezone

from config.apps.accounts.models import User, Student, Instructor, Subject
from config.apps.cash.models import InstructorMonthlyRank, LectureRentalHistory
from config.apps.lecture.models import Lecture
from config.apps.tutoring.models import InstructorInfo, TutoringPost
from config.apps.block.models import Block

class MainAPIViewSetTests(APITestCase):

    def setUp(self):
        # Create users
        self.student_user = User.objects.create_user(
            username="student_seoul_login", password="password", region="서울 강남구", user_name="student_seoul"
        )
        self.student = Student.objects.create(user=self.student_user)

        self.instructor_user = User.objects.create_user(
            username="instructor_seoul_login", password="password", region="서울 송파구", user_name="instructor_seoul"
        )
        self.instructor = Instructor.objects.create(user=self.instructor_user, university="서울대")

        self.other_instructor_user = User.objects.create_user(
            username="instructor_busan_login", password="password", region="부산 해운대구", user_name="instructor_busan"
        )
        self.other_instructor = Instructor.objects.create(user=self.other_instructor_user, university="부산대")

        # Create InstructorInfo for active instructors
        InstructorInfo.objects.create(instructor=self.instructor)
        # We do NOT create TutoringProfile for other_instructor to make sure only ones with profile show up

        # Create active TutoringPost for active students
        TutoringPost.objects.create(student=self.student, title="Seoul student post", is_active=True)

        # Create subjects 
        subj = Subject.objects.create(number=1)
        self.instructor.subjects.add(subj)

        now = timezone.now()
        this_month = now.month
        this_year = now.year

        last_month = this_month - 1
        last_year = this_year
        if last_month == 0:
            last_month = 12
            last_year -= 1
        
        InstructorMonthlyRank.objects.create(
            year=last_year,
            month=last_month,
            instructor=self.instructor,
            total_cash=5000,
            rank=1
        )

        self.lecture = Lecture.objects.create(
            title="Test Lecture",
            instructor=self.instructor,
            price=1000,
            is_delete=False
        )

        LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.student_user,
            purchased_cash=1000,
            remaining_cash=0,
            is_canceled=False,
            is_settled=False
        )
        
        history = LectureRentalHistory.objects.first()
        history.created_at = now
        history.save()

    def test_student_main_api(self):
        # 1. First test regular retrieval
        url = reverse('student-main')
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify it returns instructors from '서울'
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user_name'], "instructor_seoul")
        self.assertEqual(response.data[0]['average_rate'], 0.0)

        # 2. Add an Instructor profile to the logged-in student user to test self-lookup exclusion
        student_instructor = Instructor.objects.create(user=self.student_user, university="연세대")
        InstructorInfo.objects.create(instructor=student_instructor)
        
        # When requesting now, student_user should NOT see themselves in the recommended list
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should still be 1 (only instructor_seoul), and NOT containing student_seoul
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user_name'], "instructor_seoul")

    def test_main_recommendations_hide_bidirectionally_blocked_users(self):
        Block.objects.create(
            user=self.instructor_user,
            blocked_user=self.student_user,
        )

        self.client.force_authenticate(user=self.student_user)
        student_response = self.client.get(reverse('student-main'))
        self.assertEqual(student_response.status_code, status.HTTP_200_OK)
        self.assertEqual(student_response.data, [])

        self.client.force_authenticate(user=self.instructor_user)
        instructor_response = self.client.get(reverse('instructor-main'))
        self.assertEqual(instructor_response.status_code, status.HTTP_200_OK)
        self.assertEqual(instructor_response.data['recommended_students'], [])

    def test_instructor_main_api(self):
        # 1. First test regular retrieval
        url = reverse('instructor-main')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertIsNotNone(response.data.get('previous_month_rank_info'))
        self.assertEqual(response.data['previous_month_rank_info']['total_cash'], 5000)
        self.assertEqual(response.data['previous_month_rank_info']['rank'], 1)

        self.assertEqual(response.data.get('this_month_total_cash'), 1000)

        self.assertEqual(len(response.data.get('recommended_students')), 1)
        self.assertEqual(response.data.get('recommended_students')[0]['user_name'], "student_seoul")

        # 2. Add a Student profile and active TutoringPost to the logged-in instructor user to test self-lookup exclusion
        instructor_student = Student.objects.create(user=self.instructor_user)
        TutoringPost.objects.create(student=instructor_student, title="Instructor as student post", is_active=True)

        # When requesting now, instructor_user should NOT see themselves in the recommended list
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should still be 1 (only student_seoul), and NOT containing instructor_seoul
        self.assertEqual(len(response.data.get('recommended_students')), 1)
        self.assertEqual(response.data.get('recommended_students')[0]['user_name'], "student_seoul")
