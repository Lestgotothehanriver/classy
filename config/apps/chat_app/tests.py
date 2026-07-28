from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from config.apps.accounts.models import Instructor, InstructorLike, Student, User
from config.apps.chat_app.models import ChatRoom
from config.apps.tutoring.models import TutoringPost


class ChatRoomOpponentProfileImageTest(TestCase):
    """채팅방 목록이 현재 사용자가 아닌 상대방 사진을 반환하는지 검증한다."""

    def setUp(self):
        self.client = APIClient()
        self.student_user = User.objects.create_user(
            username="student_chat_image",
            user_name="student_chat_image",
            password="pass1234",
            profile_image="profile_images/student.jpg",
        )
        self.instructor_user = User.objects.create_user(
            username="instructor_chat_image",
            user_name="instructor_chat_image",
            password="pass1234",
            profile_image="profile_images/instructor.jpg",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(
            user=self.instructor_user,
            university="테스트대학교",
        )
        self.post = TutoringPost.objects.create(student=self.student)
        ChatRoom.objects.create(
            student=self.student,
            instructor=self.instructor,
            post=self.post,
        )

    def _authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_student_role_returns_instructor_profile_image(self):
        self._authenticate(self.student_user)

        response = self.client.get("/chatrooms/", {"role": "student"})

        self.assertEqual(response.status_code, 200)
        image_url = response.json()[0]["opponent_info"]["profile_image"]
        self.assertTrue(image_url.endswith("/media/profile_images/instructor.jpg"))
        self.assertNotIn("student.jpg", image_url)

    def test_instructor_role_returns_student_profile_image(self):
        self._authenticate(self.instructor_user)

        response = self.client.get("/chatrooms/", {"role": "instructor"})

        self.assertEqual(response.status_code, 200)
        image_url = response.json()[0]["opponent_info"]["profile_image"]
        self.assertTrue(image_url.endswith("/media/profile_images/student.jpg"))
        self.assertNotIn("instructor.jpg", image_url)

    def test_student_chat_like_uses_room_liked_by(self):
        """학생의 채팅방 찜(is_liked)은 강사 프로필 좋아요가 아니라
        채팅방 자체의 liked_by를 기준으로 반영되어야 한다."""
        self._authenticate(self.student_user)

        before = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(before.status_code, 200)
        self.assertFalse(before.json()[0]["is_liked"])

        # 강사 프로필 좋아요만으로는 채팅방 찜이 켜지지 않는다.
        InstructorLike.objects.create(
            student=self.student,
            instructor=self.instructor,
        )
        still = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(still.status_code, 200)
        self.assertFalse(still.json()[0]["is_liked"])

        # 채팅방 자체를 찜하면 is_liked가 True가 된다.
        room = ChatRoom.objects.first()
        room.liked_by.add(self.student_user)

        after = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(after.status_code, 200)
        self.assertTrue(after.json()[0]["is_liked"])


# Create your tests here.
