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
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.instructor_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
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

        # 사용자 생성 (학생 1명 + 강사 4명)
        self.student_user = User.objects.create_user(username="student", user_name="student", password="pass1234")
        self.inst_user_no_pending = User.objects.create_user(username="inst_no_pending", user_name="inst_no_pending", password="pass1234")
        self.inst_user_pending = User.objects.create_user(username="inst_pending", user_name="inst_pending", password="pass1234")
        self.inst_user_verified = User.objects.create_user(username="inst_verified", user_name="inst_verified", password="pass1234")
        self.inst_user_suspended = User.objects.create_user(username="inst_suspended", user_name="inst_suspended", password="pass1234")

        # 프로필 생성
        self.student = Student.objects.create(user=self.student_user)
        self.inst_no_pending = Instructor.objects.create(user=self.inst_user_no_pending, university="No Pending Univ")
        self.inst_pending = Instructor.objects.create(user=self.inst_user_pending, university="Pending Univ")
        self.inst_verified = Instructor.objects.create(user=self.inst_user_verified, university="Verified Univ")
        self.inst_suspended = Instructor.objects.create(user=self.inst_user_suspended, university="Suspended Univ")

        # InstructorInfo 생성 (info-read API 조회를 위해)
        from config.apps.tutoring.models import InstructorInfo
        self.info_no_pending = InstructorInfo.objects.create(instructor=self.inst_no_pending, cost=10000)
        self.info_pending = InstructorInfo.objects.create(instructor=self.inst_pending, cost=20000)
        self.info_verified = InstructorInfo.objects.create(instructor=self.inst_verified, cost=30000)
        self.info_suspended = InstructorInfo.objects.create(instructor=self.inst_suspended, cost=40000)

        # pending_info 생성 및 상태 설정
        PendingInstructor.objects.create(instructor_profile=self.inst_pending, status=PendingInstructor.Status.PENDING)
        PendingInstructor.objects.create(instructor_profile=self.inst_verified, status=PendingInstructor.Status.VERIFIED)
        PendingInstructor.objects.create(instructor_profile=self.inst_suspended, status=PendingInstructor.Status.SUSPENDED)

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
        suspended_data = next(x for x in results if x["id"] == self.inst_suspended.id)

        self.assertTrue(no_pending_data["is_unverified"])  # pending_info가 없으므로 True
        self.assertTrue(pending_data["is_unverified"])    # pending_info 상태가 PENDING이므로 True
        self.assertFalse(verified_data["is_unverified"])  # pending_info 상태가 VERIFIED이므로 False
        self.assertTrue(suspended_data["is_unverified"])
        self.assertEqual(no_pending_data["verification_status"], "NOT_SUBMITTED")
        self.assertEqual(pending_data["verification_status"], "PENDING")
        self.assertEqual(verified_data["verification_status"], "VERIFIED")
        self.assertEqual(suspended_data["verification_status"], "SUSPENDED")

    def test_list_instructors_filters_by_max_cost(self):
        """cost 상한 이하의 과외비를 등록한 강사만 반환한다."""
        resp = self.client.get("/tutoring/instructors/", {"cost": "25000"})

        self.assertEqual(resp.status_code, 200)
        instructor_ids = {item["id"] for item in resp.json()["results"]}
        self.assertEqual(
            instructor_ids,
            {self.inst_no_pending.id, self.inst_pending.id},
        )

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
        self.assertTrue(resp.json()["is_certified"])
        self.assertEqual(resp.json()["verification_status"], "VERIFIED")

        # 4. pending_info가 SUSPENDED 상태
        resp = self.client.get(f"/tutoring/instructors/{self.inst_suspended.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_unverified"])
        self.assertFalse(resp.json()["is_certified"])
        self.assertEqual(resp.json()["verification_status"], "SUSPENDED")

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
        self.assertEqual(resp.json()["verification_status"], "VERIFIED")

        # 4. pending_info가 SUSPENDED 상태
        resp = self.client.get(f"/tutoring/instructors/{self.inst_suspended.id}/info/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_unverified"])
        self.assertFalse(resp.json()["is_certified"])
        self.assertEqual(resp.json()["verification_status"], "SUSPENDED")


class InstructorInfoRegistrationTest(TestCase):
    """InstructorInfo가 등록되면 Instructor의 is_tutoring 필드가 True로 변경되는지 검증"""

    def setUp(self):
        self.client = APIClient()
        self.inst_user = User.objects.create_user(username="inst_user", user_name="inst_user", password="pass1234")
        self.instructor = Instructor.objects.create(user=self.inst_user, university="Test Univ")
        
        # Verify initial state of is_tutoring is False
        self.assertFalse(self.instructor.is_tutoring)

    def test_direct_creation_sets_is_tutoring_true(self):
        """InstructorInfo 모델을 직접 생성할 때 is_tutoring 필드가 True로 변경되는지 검증"""
        from config.apps.tutoring.models import InstructorInfo
        InstructorInfo.objects.create(
            instructor=self.instructor,
            cost=25000,
            schedule="Sat, Sun",
            method="대면",
            location="Seoul"
        )
        self.instructor.refresh_from_db()
        self.assertTrue(self.instructor.is_tutoring)

    def test_api_creation_sets_is_tutoring_true(self):
        """API를 통해 InstructorInfo를 생성할 때 is_tutoring 필드가 True로 변경되는지 검증"""
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.inst_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        payload = {
            "cost": 30000,
            "schedule": "Monday",
            "method": "비대면",
            "location": "Online"
        }
        resp = self.client.post("/tutoring/instructor-info/", data=payload, format="json")
        self.assertEqual(resp.status_code, 201)

        self.instructor.refresh_from_db()
        self.assertTrue(self.instructor.is_tutoring)

    def test_patch_response_contains_existing_subjects_and_regions(self):
        """PATCH 응답은 수정 폼을 다시 채울 수 있는 전체 데이터를 반환한다."""
        from config.apps.accounts.models import Subject
        from config.apps.tutoring.models import InstructorInfo, Region
        from rest_framework.authtoken.models import Token

        subject = Subject.objects.create(number=1)
        region = Region.objects.create(number=1)
        info = InstructorInfo.objects.create(
            instructor=self.instructor,
            cost=30000,
            schedule="Monday",
            method="대면",
            location=str(region),
        )
        info.subjects.add(subject)
        info.regions.add(region)

        token, _ = Token.objects.get_or_create(user=self.inst_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.patch(
            f"/tutoring/instructor-info/{info.id}/",
            {"schedule": "Tuesday"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schedule"], "Tuesday")
        self.assertEqual(response.json()["subjects"][0]["number"], subject.number)
        self.assertEqual(response.json()["regions"][0]["id"], region.id)


class TutoringPostPatchRepresentationTest(TestCase):
    """공고 PATCH 응답이 다음 수정 화면을 채울 수 있는지 검증한다."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="post_owner",
            user_name="post_owner",
            password="pass1234",
        )
        self.student = Student.objects.create(user=self.user)
        from config.apps.accounts.models import Subject
        from config.apps.tutoring.models import Region
        from rest_framework.authtoken.models import Token

        self.subject = Subject.objects.create(number=1)
        self.region = Region.objects.create(number=1)
        self.post = TutoringPost.objects.create(
            student=self.student,
            title="기존 제목",
            sex="남성",
            age=17,
            grade="고1",
            field="이과",
            method="대면",
            cost=300000,
            schedule="주말",
            situation="내신 대비",
            etc="친절한 설명",
        )
        self.post.subjects.add(self.subject)
        self.post.regions.add(self.region)
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_patch_response_contains_full_detail(self):
        response = self.client.patch(
            f"/tutoring/posts/write/{self.post.id}/",
            {"schedule": "평일 저녁"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "기존 제목")
        self.assertEqual(data["schedule"], "평일 저녁")
        self.assertEqual(data["situation"], "내신 대비")
        self.assertEqual(data["subjects"][0]["number"], self.subject.number)
        self.assertEqual(data["regions"][0]["id"], self.region.id)


class TutoringPostViewCountTest(LikeSortingTestBase):
    """강사가 공고 상세를 조회할 때 조회수 증가값을 반환하는지 검증한다."""

    def setUp(self):
        super().setUp()
        from rest_framework.authtoken.models import Token

        self.post = TutoringPost.objects.create(
            student=self.student1,
            title="수학 과외를 구합니다",
            view_count=0,
        )
        token, _ = Token.objects.get_or_create(user=self.instructor_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_instructor_detail_view_increments_and_returns_view_count(self):
        first_response = self.client.get(f"/tutoring/posts/{self.post.id}/")
        second_response = self.client.get(f"/tutoring/posts/{self.post.id}/")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["view_count"], 1)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["view_count"], 2)
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 2)


class TutoringPostSearchAPITest(LikeSortingTestBase):
    """과외 구인 공고 통합 검색(search) API 테스트"""

    def setUp(self):
        super().setUp()
        from config.apps.accounts.models import Subject
        from config.apps.tutoring.models import TutoringPost
        from rest_framework.authtoken.models import Token

        # Subject 생성
        self.subject_korean = Subject.objects.create(number=1)  # 초등국어
        self.subject_math = Subject.objects.create(number=3)    # 초등수학

        # 학생 유저 이름 커스텀 설정
        self.student_user1.user_name = "홍길동"
        self.student_user1.save()
        self.student_user2.user_name = "이순신"
        self.student_user2.save()

        # 공고 생성
        self.post_korean = TutoringPost.objects.create(
            student=self.student1,
            title="국어 공부 같이해요",
            situation="기초가 부족합니다.",
            etc="주말 수업 선호",
            is_active=True
        )
        self.post_korean.subjects.add(self.subject_korean)

        self.post_math = TutoringPost.objects.create(
            student=self.student2,
            title="수학 등급 올리고 싶어요",
            situation="심화 학습 원해요.",
            etc="친절한 선생님",
            is_active=True
        )
        self.post_math.subjects.add(self.subject_math)

        # 강사 토큰으로 인증
        self.instructor_token, _ = Token.objects.get_or_create(user=self.instructor_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.instructor_token.key}")

    def test_search_by_title(self):
        """제목으로 검색"""
        resp = self.client.get("/tutoring/posts/", {"search": "국어 공부"})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.post_korean.id)

    def test_search_by_situation(self):
        """학생 상황(situation)으로 검색"""
        resp = self.client.get("/tutoring/posts/", {"search": "심화"})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.post_math.id)

    def test_search_by_etc(self):
        """기타 요청사항(etc)으로 검색"""
        resp = self.client.get("/tutoring/posts/", {"search": "주말 수업"})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.post_korean.id)

    def test_search_by_student_name(self):
        """학생 닉네임으로 검색"""
        resp = self.client.get("/tutoring/posts/", {"search": "이순신"})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.post_math.id)

    def test_search_by_subject_name(self):
        """과목 이름으로 검색"""
        resp = self.client.get("/tutoring/posts/", {"search": "수학"})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.post_math.id)


class TutoringResourceAPITest(LikeSortingTestBase):
    """TutoringResource CRUD 및 검증(과목 3개 제한) 테스트"""

    def setUp(self):
        super().setUp()
        from config.apps.accounts.models import Subject
        # Subject들 생성
        self.subject1 = Subject.objects.create(number=1)
        self.subject2 = Subject.objects.create(number=2)
        self.subject3 = Subject.objects.create(number=3)
        self.subject4 = Subject.objects.create(number=4)

    def test_create_tutoring_resource_with_3_or_less_subjects(self):
        """과목 3개 이하로 TutoringResource 생성 시 성공"""
        payload = {
            "student": self.student1.id,
            "instructor": self.inst1.id,
            "subject": [self.subject1.number, self.subject2.number],
            "class_type": "단기 수업",
            "first_month_fee": 300000,
        }
        resp = self.client.post("/tutoring/resources/", data=payload, format="json")
        self.assertEqual(resp.status_code, 201)
        
        # 상세 데이터 응답 검증
        data = resp.json()
        self.assertEqual(len(data["subject"]), 2)
        self.assertEqual(data["subject"][0]["number"], self.subject1.number)
        self.assertEqual(data["subject"][1]["number"], self.subject2.number)

    def test_create_tutoring_resource_with_more_than_3_subjects(self):
        """과목 3개 초과로 TutoringResource 생성 시 실패 (400 Bad Request)"""
        payload = {
            "student": self.student1.id,
            "instructor": self.inst1.id,
            "subject": [self.subject1.number, self.subject2.number, self.subject3.number, self.subject4.number],
            "class_type": "단기 수업",
            "first_month_fee": 300000,
        }
        resp = self.client.post("/tutoring/resources/", data=payload, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("subject", resp.json())
        self.assertEqual(resp.json()["subject"][0], "과외 성사당 과목은 최대 3개까지만 제한하여 등록할 수 있습니다.")


class StudentProposalRoomTest(LikeSortingTestBase):
    """학생의 과외 상담 요청 및 첫 번째 메시지 문구 테스트"""

    def setUp(self):
        super().setUp()
        self.post = TutoringPost.objects.create(student=self.student1, is_active=True)

    def test_student_propose_initial_message_text(self):
        """학생이 강사에게 과외 제안 시 첫 번째 메시지의 수정된 텍스트 확인"""
        from config.apps.chat_app.models import ChatRoom, ChatMessage
        
        payload = {
            "instructor_id": self.inst1.id,
            "post_id": self.post.id,
        }
        resp = self.client.post("/tutoring/propose-to-instructor/", data=payload, format="json")
        self.assertEqual(resp.status_code, 201)
        
        room_id = resp.json()["room_id"]
        room = ChatRoom.objects.get(id=room_id)
        
        # 첫 번째 메시지 조회
        messages = ChatMessage.objects.filter(room=room).order_by("created_at")
        self.assertEqual(messages.count(), 1)
        first_msg = messages.first()
        
        expected_text = f"{self.student_user1.user_name} 님이 선생님에게 과외 상담 요청을 보냈습니다."
        self.assertEqual(first_msg.text, expected_text)


class SelfLookupPreventionTest(LikeSortingTestBase):
    """학생 과외 공고 및 선생님 프로필 조회에서 본인 조회 방지 테스트"""

    def setUp(self):
        super().setUp()
        self.post1 = TutoringPost.objects.create(student=self.student1, is_active=True)
        self.post2 = TutoringPost.objects.create(student=self.student2, is_active=True)

    def test_student_cannot_see_own_tutoring_posts(self):
        """학생이 /tutoring/posts/ 조회 시 자신의 공고는 제외되어야 함"""
        # student_user1 (student1)로 로그인된 상태
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.student_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resp = self.client.get("/tutoring/posts/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]
        
        # student1이 작성한 post1은 제외되고 student2가 작성한 post2만 보여야 함
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.post2.id)

    def test_instructor_cannot_see_own_profile(self):
        """강사가 /tutoring/instructors/ 조회 시 자신의 프로필은 제외되어야 함"""
        # instructor_user1 (inst1)로 로그인
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.instructor_user1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resp = self.client.get("/tutoring/instructors/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]

        # inst1 (자기 자신)은 제외되고 inst2, inst3만 보여야 함
        self.assertEqual(len(data), 2)
        inst_ids = {item["id"] for item in data}
        self.assertNotIn(self.inst1.id, inst_ids)
        self.assertIn(self.inst2.id, inst_ids)
        self.assertIn(self.inst3.id, inst_ids)

