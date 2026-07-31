from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from unittest.mock import patch

from config.apps.accounts.models import Instructor, InstructorLike, Student, User
from config.apps.chat_app.models import ChatMessage, ChatRoom
from config.apps.tutoring.models import TutoringPost
from config.apps.notification.helpers import notify_tutoring_request


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

    def test_liked_filter_returns_only_favorited_rooms(self):
        """?liked=true 는 현재 유저가 찜(liked_by)한 채팅방만 반환한다.
        선생님도 채팅방 기준으로 찜/필터할 수 있어야 한다."""
        self._authenticate(self.instructor_user)

        # 찜 전: liked=true 면 빈 목록
        empty = self.client.get(
            "/chatrooms/", {"role": "instructor", "liked": "true"}
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(len(empty.json()), 0)

        # 채팅방을 찜하면 필터 결과에 포함된다.
        room = ChatRoom.objects.first()
        room.liked_by.add(self.instructor_user)

        liked = self.client.get(
            "/chatrooms/", {"role": "instructor", "liked": "true"}
        )
        self.assertEqual(liked.status_code, 200)
        self.assertEqual(len(liked.json()), 1)
        self.assertTrue(liked.json()[0]["is_liked"])

        # liked 파라미터가 없으면 찜 여부와 무관하게 전체를 반환한다.
        all_rooms = self.client.get("/chatrooms/", {"role": "instructor"})
        self.assertEqual(len(all_rooms.json()), 1)

    def test_class_status_reflects_tutoring_registration(self):
        """수업 종류 칩(class_status)은 채팅방의 성사 등록(TutoringRegistration)을 따른다."""
        from datetime import date
        from config.apps.tutoring.models import TutoringRegistration

        self._authenticate(self.student_user)
        room = ChatRoom.objects.first()

        # 등록 없음 → None (칩 없음)
        resp = self.client.get("/chatrooms/", {"role": "student"})
        self.assertIsNone(resp.json()[0]["class_status"])

        # 계약 정보 수집 중(COLLECTING) → 'unregistered' (성사 등록 진행중)
        reg = TutoringRegistration.objects.create(
            student=self.student_user,
            instructor=self.instructor_user,
            chat_room=room,
            subject="고등 수학",
            start_date=date(2026, 1, 1),
        )
        resp = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(resp.json()[0]["class_status"], "unregistered")

        # 등록 완료 + 정규 → 'regular'
        reg.contract_status = "REGISTERED"
        reg.confirmed_class_type = "REGULAR"
        reg.save()
        resp = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(resp.json()[0]["class_status"], "regular")

        # 단기 → 'short_term'
        reg.confirmed_class_type = "SHORT_TERM"
        reg.save()
        resp = self.client.get("/chatrooms/", {"role": "student"})
        self.assertEqual(resp.json()[0]["class_status"], "short_term")

        # 취소 → None
        reg.contract_status = "CANCELLED"
        reg.save()
        resp = self.client.get("/chatrooms/", {"role": "student"})
        self.assertIsNone(resp.json()[0]["class_status"])

    def test_read_marks_all_room_messages_through_target(self):
        """REST 읽음 처리는 WebSocket과 동일하게 대상 메시지 이하를 모두 갱신한다."""
        self._authenticate(self.instructor_user)
        room = ChatRoom.objects.first()
        older = ChatMessage.objects.create(
            room=room,
            sender=self.student_user,
            text="첫 번째 메시지",
        )
        target = ChatMessage.objects.create(
            room=room,
            sender=self.student_user,
            text="두 번째 메시지",
        )
        newer = ChatMessage.objects.create(
            room=room,
            sender=self.student_user,
            text="세 번째 메시지",
        )

        response = self.client.post(
            f"/chatrooms/{room.pk}/read/{target.pk}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["read_count"], 2)
        self.assertEqual(response.json()["room_id"], str(room.pk))
        self.assertEqual(response.json()["message_id"], str(target.pk))
        self.assertEqual(response.json()["unread_count"], 1)
        self.assertTrue(older.read_by.filter(pk=self.instructor_user.pk).exists())
        self.assertTrue(target.read_by.filter(pk=self.instructor_user.pk).exists())
        self.assertFalse(newer.read_by.filter(pk=self.instructor_user.pk).exists())

    def test_read_rejects_a_non_participant(self):
        """REST 읽음 처리는 채팅방 참가자가 아닌 사용자를 거부한다."""
        outsider = User.objects.create_user(
            username="chat_read_outsider",
            user_name="chat_read_outsider",
            password="pass1234",
        )
        self._authenticate(outsider)
        room = ChatRoom.objects.first()
        message = ChatMessage.objects.create(
            room=room,
            sender=self.student_user,
            text="참가자만 읽을 수 있음",
        )

        response = self.client.post(
            f"/chatrooms/{room.pk}/read/{message.pk}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_read_through_own_latest_message_marks_prior_counterpart_messages(self):
        """최신 메시지가 내 메시지여도 그 이전 상대 메시지까지 읽음 처리한다."""
        self._authenticate(self.instructor_user)
        room = ChatRoom.objects.first()
        incoming = ChatMessage.objects.create(
            room=room,
            sender=self.student_user,
            text="상대 메시지",
        )
        own_latest = ChatMessage.objects.create(
            room=room,
            sender=self.instructor_user,
            text="내 답장",
        )

        response = self.client.post(
            f"/chatrooms/{room.pk}/read/{own_latest.pk}/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertTrue(
            incoming.read_by.filter(pk=self.instructor_user.pk).exists()
        )

    @patch("config.apps.notification.fcm.send_push_to_user")
    def test_tutoring_request_push_contains_target_role(self, send_push):
        """역할성 FCM payload는 수신 역할을 명시한다."""
        room = ChatRoom.objects.first()

        notify_tutoring_request(room)

        self.assertEqual(
            send_push.call_args.kwargs["data"]["target_role"],
            "instructor",
        )


# Create your tests here.
