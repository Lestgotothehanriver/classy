from django.test import TestCase
from rest_framework.test import APIClient
from config.apps.accounts.models import User, Student, Instructor, InstructorLike
from config.apps.tutoring.models import TutoringPost, TutoringPostLike
from config.apps.pending.models import PendingInstructor


class LikeSortingTestBase(TestCase):
    """좋아요 정렬 테스트를 위한 공통 setUp"""

    def setUp(self):
        self.client = APIClient()

        # 유저 생성 (학생 2명 + 강사 3명)
        self.student_user1 = User.objects.create_user(username="student1", user_name="student1", password="pass1234")
        self.student_user2 = User.objects.create_user(username="student2", user_name="student2", password="pass1234")
        self.instructor_user1 = User.objects.create_user(username="inst1", user_name="inst1", password="pass1234")
        self.instructor_user2 = User.objects.create_user(username="inst2", user_name="inst2", password="pass1234")
        self.instructor_user3 = User.objects.create_user(username="inst3", user_name="inst3", password="pass1234")

        # 프로필 생성
        self.student1 = Student.objects.create(user=self.student_user1)
        self.student2 = Student.objects.create(user=self.student_user2)
        self.inst1 = Instructor.objects.create(user=self.instructor_user1, university="A대학교")
        self.inst2 = Instructor.objects.create(user=self.instructor_user2, university="B대학교")
        self.inst3 = Instructor.objects.create(user=self.instructor_user3, university="C대학교")

        # 강사 승인 상태(VERIFIED) 생성
        PendingInstructor.objects.create(instructor_profile=self.inst1, status=PendingInstructor.Status.VERIFIED)
        PendingInstructor.objects.create(instructor_profile=self.inst2, status=PendingInstructor.Status.VERIFIED)
        PendingInstructor.objects.create(instructor_profile=self.inst3, status=PendingInstructor.Status.VERIFIED)

        # 기본적으로 student_user1로 인증 설정
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


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
        data = resp.json()["results"]
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
        data = resp.json()["results"]
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
        data = resp.json()["results"]
        inst3_data = next(d for d in data if d["id"] == self.inst3.id)
        self.assertEqual(inst3_data["like_count"], 0)

    def test_liked_true_filter(self):
        """?liked=true → 자신이 좋아요한 강사만 반환"""
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        
        resp = self.client.get("/tutoring/instructors/", {"liked": "true"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]
        
        # student1은 inst1, inst2를 좋아요함
        self.assertEqual(len(data), 2)
        liked_ids = {item["id"] for item in data}
        self.assertIn(self.inst1.id, liked_ids)
        self.assertIn(self.inst2.id, liked_ids)
        self.assertNotIn(self.inst3.id, liked_ids)
        
        # is_liked 필드가 모두 True여야 함
        for item in data:
            self.assertTrue(item["is_liked"])

    def test_liked_false_filter(self):
        """?liked=false → 자신이 좋아요하지 않은 강사만 반환"""
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        
        resp = self.client.get("/tutoring/instructors/", {"liked": "false"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]
        
        # student1은 inst3만 좋아요하지 않음
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.inst3.id)
        self.assertFalse(data[0]["is_liked"])
        
    def test_is_liked_field_in_response(self):
        """응답에 is_liked 필드가 존재하고 값이 정확한지 확인"""
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        
        resp = self.client.get("/tutoring/instructors/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]
        
        # 기본 정렬(최신순)이므로 inst3 > inst2 > inst1
        self.assertEqual(len(data), 3)
        likes_map = {item["id"]: item["is_liked"] for item in data}
        self.assertEqual(likes_map[self.inst1.id], True)
        self.assertEqual(likes_map[self.inst2.id], True)
        self.assertEqual(likes_map[self.inst3.id], False)

    def test_unauthenticated_liked_false(self):
        """비인증 사용자는 401"""
        client = APIClient()
        resp = client.get("/tutoring/instructors/")
        self.assertEqual(resp.status_code, 401)


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
        data = resp.json()["results"]
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
        data = resp.json()["results"]
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
        data = resp.json()["results"]
        ids = [d["id"] for d in data]
        self.assertNotIn(self.post1.id, ids)
        self.assertEqual(len(data), 2)


class InstructorLikeAPITest(LikeSortingTestBase):
    """강사 좋아요 생성/삭제 API 테스트"""

    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token
        self.student_token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.instructor_token, _ = Token.objects.get_or_create(user=self.instructor_user1)

    def test_student_can_like_instructor(self):
        """학생이 강사를 좋아요할 수 있음 (201)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        resp = self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["is_liked"], True)

    def test_toggle_like_removes_like(self):
        """같은 강사를 두 번 좋아요하면 해제됨 (200)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        resp = self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["is_liked"], False)

    def test_instructor_cannot_like_instructor(self):
        """강사 계정은 강사 좋아요 불가 (403)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        resp = self.client.post(f"/tutoring/instructors/{self.inst2.id}/like/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_returns_401(self):
        """비로그인 시 401"""
        self.client.credentials()  # Clear credentials
        resp = self.client.post(f"/tutoring/instructors/{self.inst1.id}/like/")
        self.assertEqual(resp.status_code, 401)


class TutoringPostLikeAPITest(LikeSortingTestBase):
    """공고 좋아요 생성/삭제 API 테스트"""

    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token
        self.instructor_token, _ = Token.objects.get_or_create(user=self.instructor_user1)
        self.student_token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.post1 = TutoringPost.objects.create(student=self.student1, is_active=True)

    def test_instructor_can_like_post(self):
        """강사가 공고를 좋아요할 수 있음 (201)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["is_liked"], True)

    def test_toggle_like_removes_post_like(self):
        """같은 공고를 두 번 좋아요하면 해제됨 (200)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")
        self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["is_liked"], False)

    def test_student_cannot_like_post(self):
        """학생 계정은 공고 좋아요 불가 (403)"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.student_token.key}")
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_returns_401(self):
        """비로그인 시 401"""
        self.client.credentials()  # Clear credentials
        resp = self.client.post(f"/tutoring/posts/{self.post1.id}/like/")
        self.assertEqual(resp.status_code, 401)


class InstructorUnverifiedStatusTest(TestCase):
    """학생이 강사 프로필을 조회할 때 is_unverified 필드가 정확히 반환되는지 확인하는 테스트"""

    def setUp(self):
        self.client = APIClient()

        # 사용자 생성 (학생 1명 + 강사 3명)
        self.student_user = User.objects.create_user(username="student", user_name="student", password="pass1234")
        self.inst_user_no_pending = User.objects.create_user(username="inst_no_pending", user_name="inst_no_pending", password="pass1234")
        self.inst_user_pending = User.objects.create_user(username="inst_pending", user_name="inst_pending", password="pass1234")
        self.inst_user_verified = User.objects.create_user(username="inst_verified", user_name="inst_verified", password="pass1234")

        # 프로필 생성
        self.student = Student.objects.create(user=self.student_user)
        self.inst_no_pending = Instructor.objects.create(user=self.inst_user_no_pending, university="No Pending Univ")
        self.inst_pending = Instructor.objects.create(user=self.inst_user_pending, university="Pending Univ")
        self.inst_verified = Instructor.objects.create(user=self.inst_user_verified, university="Verified Univ")

        # InstructorInfo 생성 (info-read API 조회를 위해)
        from config.apps.tutoring.models import InstructorInfo
        self.info_no_pending = InstructorInfo.objects.create(instructor=self.inst_no_pending, cost=10000)
        self.info_pending = InstructorInfo.objects.create(instructor=self.inst_pending, cost=20000)
        self.info_verified = InstructorInfo.objects.create(instructor=self.inst_verified, cost=30000)

        # pending_info 생성 및 상태 설정
        PendingInstructor.objects.create(instructor_profile=self.inst_pending, status=PendingInstructor.Status.PENDING)
        PendingInstructor.objects.create(instructor_profile=self.inst_verified, status=PendingInstructor.Status.VERIFIED)

        # 학생으로 인증
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.student_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_list_instructors_returns_is_unverified_correctly(self):
        """강사 목록 조회 시 각 강사의 미인증 여부가 정확히 반환되는지 확인"""
        resp = self.client.get("/tutoring/instructors/")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]

        # 3명의 강사 데이터 확인
        no_pending_data = next(x for x in results if x["id"] == self.inst_no_pending.id)
        pending_data = next(x for x in results if x["id"] == self.inst_pending.id)
        verified_data = next(x for x in results if x["id"] == self.inst_verified.id)

        self.assertTrue(no_pending_data["is_unverified"])  # pending_info가 없으므로 True
        self.assertTrue(pending_data["is_unverified"])    # pending_info 상태가 PENDING이므로 True
        self.assertFalse(verified_data["is_unverified"])  # pending_info 상태가 VERIFIED이므로 False

    def test_retrieve_instructor_detail_returns_is_unverified_correctly(self):
        """특정 강사 상세 조회 시 미인증 여부가 정확히 반환되는지 확인"""
        # 1. pending_info 없음
        resp = self.client.get(f"/tutoring/instructors/{self.inst_no_pending.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_unverified"])

        # 2. pending_info가 PENDING 상태
        resp = self.client.get(f"/tutoring/instructors/{self.inst_pending.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_unverified"])

        # 3. pending_info가 VERIFIED 상태
        resp = self.client.get(f"/tutoring/instructors/{self.inst_verified.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_unverified"])

    def test_retrieve_instructor_info_returns_is_unverified_correctly(self):
        """특정 강사 과외 소개 상세 조회 시 미인증 여부가 정확히 반환되는지 확인"""
        # 1. pending_info 없음
        resp = self.client.get(f"/tutoring/instructors/{self.inst_no_pending.id}/info/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_unverified"])

        # 2. pending_info가 PENDING 상태
        resp = self.client.get(f"/tutoring/instructors/{self.inst_pending.id}/info/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_unverified"])

        # 3. pending_info가 VERIFIED 상태
        resp = self.client.get(f"/tutoring/instructors/{self.inst_verified.id}/info/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_unverified"])
