from datetime import date

from rest_framework.test import APIClient, APITestCase

from config.apps.accounts.models import Instructor, Student, Subject, User
from config.apps.chat_app.models import ChatRoom
from config.apps.tutoring.models import (
    InstructorReview,
    StudentReview,
    TutoringPost,
    TutoringRegistration,
    TutoringResource,
)


class ResourceReviewApiTest(APITestCase):
    """운영 확인된 성사 리소스 단위 리뷰 계약을 검증합니다."""

    def setUp(self):
        self.student_user = User.objects.create_user(
            username="resource_student",
            user_name="리소스학생",
            password="password",
            sex="여성",
            region="서울 강남구",
        )
        self.instructor_user = User.objects.create_user(
            username="resource_instructor",
            user_name="리소스강사",
            password="password",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(
            user=self.instructor_user,
            university="클래시대학교",
            department="수학교육과",
            student_number="20241234",
        )
        self.subject = Subject.objects.create(number=7)
        self.post = TutoringPost.objects.create(
            student=self.student,
            title="수학 수업",
            sex="여성",
            grade="고2",
            field="문과",
        )
        self.post.subjects.add(self.subject)
        self.chat_room = ChatRoom.objects.create(
            student=self.student,
            instructor=self.instructor,
            post=self.post,
        )
        self.registration = TutoringRegistration.objects.create(
            student=self.student_user,
            instructor=self.instructor_user,
            chat_room=self.chat_room,
            subject=self.subject.name,
            start_date=date(2026, 7, 1),
        )
        self.resource = TutoringResource.objects.create(
            student=self.student,
            instructor=self.instructor,
            registration=self.registration,
            class_type="장기 수업",
            fee_payment_status="PAID",
        )
        self.resource.subject.add(self.subject)

        self.student_client = APIClient()
        self.student_client.force_authenticate(self.student_user)
        self.instructor_client = APIClient()
        self.instructor_client.force_authenticate(self.instructor_user)

    def test_both_review_types_are_created_per_paid_resource(self):
        instructor_response = self.student_client.post(
            "/tutoring/reviews/instructor/",
            {
                "resource": self.resource.pk,
                "instructor": self.instructor.pk,
                "professionalism": 5,
                "teaching_skill": 4,
                "punctuality": 5,
                "comment": "좋은 수업이었습니다.",
            },
            format="json",
        )
        self.assertEqual(instructor_response.status_code, 201)
        instructor_review = InstructorReview.objects.get()
        self.assertEqual(instructor_review.resource, self.resource)
        self.assertEqual(
            list(instructor_review.subjects.values_list("number", flat=True)),
            [self.subject.number],
        )

        student_response = self.instructor_client.post(
            "/tutoring/reviews/student/",
            {
                "resource": self.resource.pk,
                "student": self.student.pk,
                "rating": 4,
                "comment": "성실한 학생이었습니다.",
            },
            format="json",
        )
        self.assertEqual(student_response.status_code, 201)
        self.assertEqual(StudentReview.objects.get().resource, self.resource)

        duplicate_response = self.student_client.post(
            "/tutoring/reviews/instructor/",
            {
                "resource": self.resource.pk,
                "instructor": self.instructor.pk,
                "professionalism": 5,
                "teaching_skill": 5,
                "punctuality": 5,
                "comment": "중복 리뷰",
            },
            format="json",
        )
        self.assertEqual(duplicate_response.status_code, 400)

    def test_unpaid_resource_rating_and_comment_validation(self):
        self.resource.fee_payment_status = "PENDING"
        self.resource.save(update_fields=["fee_payment_status"])
        unpaid_response = self.student_client.post(
            "/tutoring/reviews/instructor/",
            {
                "resource": self.resource.pk,
                "instructor": self.instructor.pk,
                "professionalism": 5,
                "teaching_skill": 5,
                "punctuality": 5,
                "comment": "아직 결제 확인 전",
            },
            format="json",
        )
        self.assertEqual(unpaid_response.status_code, 400)

        self.resource.fee_payment_status = "PAID"
        self.resource.save(update_fields=["fee_payment_status"])
        invalid_response = self.student_client.post(
            "/tutoring/reviews/instructor/",
            {
                "resource": self.resource.pk,
                "instructor": self.instructor.pk,
                "professionalism": 0,
                "teaching_skill": 5,
                "punctuality": 5,
                "comment": "가" * 501,
            },
            format="json",
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn("professionalism", invalid_response.json())
        self.assertIn("comment", invalid_response.json())

    def test_other_participants_paid_resource_is_rejected(self):
        other_user = User.objects.create_user(
            username="other_resource_student",
            user_name="다른학생",
            password="password",
        )
        other_student = Student.objects.create(user=other_user)
        other_resource = TutoringResource.objects.create(
            student=other_student,
            instructor=self.instructor,
            class_type="장기 수업",
            fee_payment_status="PAID",
        )
        other_resource.subject.add(self.subject)

        response = self.student_client.post(
            "/tutoring/reviews/instructor/",
            {
                "resource": other_resource.pk,
                "instructor": self.instructor.pk,
                "professionalism": 5,
                "teaching_skill": 5,
                "punctuality": 5,
                "comment": "타인의 수업",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("resource", response.json())

    def test_resource_counterpart_and_review_card_metadata(self):
        InstructorReview.objects.create(
            resource=self.resource,
            student=self.student,
            instructor=self.instructor,
            professionalism=5,
            teaching_skill=4,
            punctuality=3,
            comment="학생 작성 리뷰",
        ).subjects.add(self.subject)
        StudentReview.objects.create(
            resource=self.resource,
            student=self.student,
            instructor=self.instructor,
            rating=4,
            comment="강사 작성 리뷰",
        )

        instructor_resources = self.instructor_client.get(
            "/tutoring/resources/",
            HTTP_X_CLASSY_ROLE="instructor",
        ).json()["results"]
        student_counterpart = instructor_resources[0]["counterpart"]
        self.assertEqual(student_counterpart["nickname"], "리소스학생")
        self.assertEqual(student_counterpart["grade"], "고2")
        self.assertEqual(student_counterpart["field"], "문과")

        student_resources = self.student_client.get(
            "/tutoring/resources/",
            HTTP_X_CLASSY_ROLE="student",
        ).json()["results"]
        instructor_counterpart = student_resources[0]["counterpart"]
        self.assertEqual(instructor_counterpart["school"], "클래시대학교")
        self.assertEqual(instructor_counterpart["department"], "수학교육과")

        instructor_reviews = self.student_client.get(
            f"/tutoring/instructors/{self.instructor.pk}/reviews/",
        ).json()["results"]
        self.assertEqual(instructor_reviews[0]["class_type"], "장기 수업")
        self.assertEqual(instructor_reviews[0]["student_region"], "서울 강남구")
        self.assertEqual(
            instructor_reviews[0]["subjects"][0]["number"],
            self.subject.number,
        )

        student_reviews = self.instructor_client.get(
            f"/tutoring/students/{self.student.pk}/reviews/",
        ).json()["results"]
        self.assertEqual(student_reviews[0]["class_type"], "장기 수업")
        self.assertEqual(
            student_reviews[0]["subjects"][0]["number"],
            self.subject.number,
        )

    def test_legacy_review_is_used_only_as_resource_fallback(self):
        legacy_review = InstructorReview.objects.create(
            student=self.student,
            instructor=self.instructor,
            professionalism=3,
            teaching_skill=3,
            punctuality=3,
            comment="기존 리뷰",
        )
        response = self.student_client.get(
            "/tutoring/resources/",
            HTTP_X_CLASSY_ROLE="student",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"][0]["my_review"]["id"],
            legacy_review.pk,
        )
