from django.test import TestCase
from rest_framework.test import APIClient
from config.apps.accounts.models import User, Student, Instructor, InstructorLike
from config.apps.tutoring.models import TutoringPost, TutoringPostLike


class LikeSortingTestBase(TestCase):
    """좋아요 정렬 테스트를 위한 공통 setUp"""

    def setUp(self):
        self.client = APIClient()

        # 유저 생성 (학생 2명 + 강사 3명)
        self.student_user1 = User.objects.create_user(username="student1", password="pass1234")
        self.student_user2 = User.objects.create_user(username="student2", password="pass1234")
        self.instructor_user1 = User.objects.create_user(username="inst1", password="pass1234")
        self.instructor_user2 = User.objects.create_user(username="inst2", password="pass1234")
        self.instructor_user3 = User.objects.create_user(username="inst3", password="pass1234")

        # 프로필 생성
        self.student1 = Student.objects.create(user=self.student_user1)
        self.student2 = Student.objects.create(user=self.student_user2)
        self.inst1 = Instructor.objects.create(user=self.instructor_user1, university="A대학교")
        self.inst2 = Instructor.objects.create(user=self.instructor_user2, university="B대학교")
        self.inst3 = Instructor.objects.create(user=self.instructor_user3, university="C대학교")


class InstructorLikeSortingTest(LikeSortingTestBase):
    """InstructorListAPIView의 좋아요 기반 정렬 테스트"""

    def setUp(self):
        super().setUp()
        # inst1: 좋아요 2개, inst2: 좋아요 1개, inst3: 좋아요 0개
        InstructorLike.objects.create(student=self.student1, instructor=self.inst1)
        InstructorLike.objects.create(student=self.student2, instructor=self.inst1)
        InstructorLike.objects.create(student=self.student1, instructor=self.inst2)

    def test_ordering_likes_returns_most_liked_first(self):
        """?ordering=likes → 좋아요 많은 강사가 먼저"""
        resp = self.client.get("/tutoring/instructors/", {"ordering": "likes"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 3)
        # inst1(2) > inst2(1) > inst3(0)
        self.assertEqual(data[0]["id"], self.inst1.id)
        self.assertEqual(data[0]["like_count"], 2)
        self.assertEqual(data[1]["id"], self.inst2.id)
        self.assertEqual(data[1]["like_count"], 1)
        self.assertEqual(data[2]["id"], self.inst3.id)
        self.assertEqual(data[2]["like_count"], 0)

    def test_ordering_latest_still_has_like_count(self):
        """기본 정렬(latest)에서도 like_count 필드가 정상 반환되는지"""
        resp = self.client.get("/tutoring/instructors/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 최신순이므로 inst3 > inst2 > inst1
        self.assertEqual(data[0]["id"], self.inst3.id)
        # like_count 필드가 존재하고 값이 정확해야 함
        like_counts = {item["id"]: item["like_count"] for item in data}
        self.assertEqual(like_counts[self.inst1.id], 2)
        self.assertEqual(like_counts[self.inst2.id], 1)
        self.assertEqual(like_counts[self.inst3.id], 0)

    def test_no_likes_returns_zero(self):
        """좋아요가 없는 강사의 like_count가 0"""
        resp = self.client.get("/tutoring/instructors/", {"ordering": "likes"})
        data = resp.json()
        inst3_data = next(d for d in data if d["id"] == self.inst3.id)
        self.assertEqual(inst3_data["like_count"], 0)


class TutoringPostLikeSortingTest(LikeSortingTestBase):
    """TutoringPostListAPIView의 좋아요 기반 정렬 테스트"""

    def setUp(self):
        super().setUp()
        # 공고 3개 생성
        self.post1 = TutoringPost.objects.create(student=self.student1, is_active=True)
        self.post2 = TutoringPost.objects.create(student=self.student1, is_active=True)
        self.post3 = TutoringPost.objects.create(student=self.student2, is_active=True)

        # post1: 좋아요 2개, post2: 좋아요 0개, post3: 좋아요 1개
        TutoringPostLike.objects.create(instructor=self.inst1, tutoring_post=self.post1)
        TutoringPostLike.objects.create(instructor=self.inst2, tutoring_post=self.post1)
        TutoringPostLike.objects.create(instructor=self.inst1, tutoring_post=self.post3)

    def test_ordering_likes_returns_most_liked_first(self):
        """?ordering=likes → 좋아요 많은 공고가 먼저"""
        resp = self.client.get("/tutoring/posts/", {"ordering": "likes"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 3)
        # post1(2) > post3(1) > post2(0)
        ids = [d["id"] for d in data]
        self.assertEqual(ids[0], self.post1.id)
        self.assertEqual(ids[1], self.post3.id)
        self.assertEqual(ids[2], self.post2.id)

    def test_ordering_latest_is_default(self):
        """기본 정렬은 최신순 (-id)"""
        resp = self.client.get("/tutoring/posts/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [d["id"] for d in data]
        # post3 > post2 > post1 (id 내림차순)
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_unique_together_prevents_duplicate_like(self):
        """같은 강사가 같은 공고에 두 번 좋아요하면 IntegrityError"""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TutoringPostLike.objects.create(instructor=self.inst1, tutoring_post=self.post1)

    def test_inactive_posts_excluded(self):
        """is_active=False 공고는 리스트에 나오지 않음"""
        self.post1.is_active = False
        self.post1.save()
        resp = self.client.get("/tutoring/posts/", {"ordering": "likes"})
        data = resp.json()
        ids = [d["id"] for d in data]
        self.assertNotIn(self.post1.id, ids)
        self.assertEqual(len(data), 2)


class InstructorLikeAPITest(LikeSortingTestBase):
    """강사 좋아요 생성/삭제 API 테스트"""

    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token
        self.student_token = Token.objects.create(user=self.student_user1)
        self.instructor_token = Token.objects.create(user=self.instructor_user1)

    def test_student_can_like_instructor(self):
        """학생이 강사를 좋아요할 수 있음 (201)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        resp = self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["detail"], "좋아요 완료")

    def test_duplicate_like_returns_409(self):
        """같은 강사를 두 번 좋아요하면 409"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        resp = self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 409)

    def test_student_can_unlike_instructor(self):
        """학생이 좋아요 취소할 수 있음 (204)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        resp = self.client.delete(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 204)

    def test_unlike_without_like_returns_404(self):
        """좋아요한 적 없는 강사를 취소하면 404"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        resp = self.client.delete(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 404)

    def test_instructor_cannot_like_instructor(self):
        """강사 계정은 강사 좋아요 불가 (403)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        resp = self.client.post(f"/tutoring/instructors/{self.inst2.id}/like/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_returns_401(self):
        """비로그인 시 401"""
        resp = self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 401)


class TutoringPostLikeAPITest(LikeSortingTestBase):
    """공고 좋아요 생성/삭제 API 테스트"""

    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token
        self.instructor_token = Token.objects.create(user=self.instructor_user1)
        self.student_token = Token.objects.create(user=self.student_user1)
        self.post1 = TutoringPost.objects.create(student=self.student1, is_active=True)

    def test_instructor_can_like_post(self):
        """강사가 공고를 좋아요할 수 있음 (201)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["detail"], "좋아요 완료")

    def test_duplicate_like_returns_409(self):
        """같은 공고를 두 번 좋아요하면 409"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 409)

    def test_instructor_can_unlike_post(self):
        """강사가 좋아요 취소할 수 있음 (204)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        resp = self.client.delete(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 204)

    def test_unlike_without_like_returns_404(self):
        """좋아요한 적 없는 공고를 취소하면 404"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        resp = self.client.delete(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 404)

    def test_student_cannot_like_post(self):
        """학생 계정은 공고 좋아요 불가 (403)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_returns_401(self):
        """비로그인 시 401"""
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 401)
