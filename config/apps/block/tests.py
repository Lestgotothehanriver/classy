from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor, Student, User
from config.apps.chat_app.models import ChatRoom
from config.apps.tutoring.models import TutoringPost

from .models import Block
from .utils import get_blocked_user_ids


class UserBlockAPITests(APITestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(
            username="block_student",
            user_name="block_student",
            password="pass1234",
        )
        self.instructor_user = User.objects.create_user(
            username="block_instructor",
            user_name="block_instructor",
            password="pass1234",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(
            user=self.instructor_user,
            university="테스트대학교",
        )
        self.post = TutoringPost.objects.create(student=self.student)
        self.room = ChatRoom.objects.create(
            student=self.student,
            instructor=self.instructor,
            post=self.post,
        )

    def test_block_create_list_and_delete_use_user_ids(self):
        self.client.force_authenticate(self.student_user)

        create_response = self.client.post(
            "/blocks/",
            {"blocked_user": self.instructor_user.pk},
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(
            create_response.data["blocked_user_info"]["id"],
            self.instructor_user.pk,
        )

        list_response = self.client.get("/blocks/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)

        delete_response = self.client.delete(
            f"/blocks/{create_response.data['id']}/"
        )
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Block.objects.exists())

    def test_block_relation_hides_chat_room_for_both_users(self):
        Block.objects.create(
            user=self.student_user,
            blocked_user=self.instructor_user,
        )

        self.assertEqual(
            get_blocked_user_ids(self.student_user),
            [self.instructor_user.pk],
        )
        self.assertEqual(
            get_blocked_user_ids(self.instructor_user),
            [self.student_user.pk],
        )

        self.client.force_authenticate(self.student_user)
        student_response = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(student_response.status_code, 200)
        self.assertEqual(student_response.data, [])

        self.client.force_authenticate(self.instructor_user)
        instructor_response = self.client.get(
            "/chatrooms/", {"role": "instructor"}
        )
        self.assertEqual(instructor_response.status_code, 200)
        self.assertEqual(instructor_response.data, [])

        self.client.force_authenticate(self.student_user)
        instructor_detail = self.client.get(
            f"/tutoring/instructors/{self.instructor.pk}/"
        )
        self.assertEqual(instructor_detail.status_code, 404)

        self.client.force_authenticate(self.instructor_user)
        post_detail = self.client.get(f"/tutoring/posts/{self.post.pk}/")
        self.assertEqual(post_detail.status_code, 404)
