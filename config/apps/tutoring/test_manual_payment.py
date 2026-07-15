import tempfile
from unittest.mock import Mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient

from config.apps.accounts.models import Instructor, Student, Subject, User
from config.apps.notification.models import Notification
from config.apps.tutoring.admin import confirm_fee_payment
from config.apps.tutoring.models import (
    InstructorReview,
    StudentReview,
    TutoringResource,
)


class ManualTutoringPaymentFlowTest(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.student_user = User.objects.create_user(
            username="manual_student", user_name="수동학생", password="password"
        )
        self.instructor_user = User.objects.create_user(
            username="manual_instructor", user_name="수동강사", password="password"
        )
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(
            user=self.instructor_user, university="Classy University"
        )
        self.subject = Subject.objects.create(number=3)
        self.instructor_client = APIClient()
        self.instructor_client.force_authenticate(self.instructor_user)
        self.student_client = APIClient()
        self.student_client.force_authenticate(self.student_user)

    def _create_resource(self):
        response = self.instructor_client.post(
            "/tutoring/resources/",
            data={
                "student": self.student.pk,
                "instructor": self.instructor.pk,
                "start_date": "2026-07-20",
                "class_type": "장기 수업",
                "subject": [self.subject.number],
                "first_month_fee": 500000,
                "fee_confirmation_file": [
                    SimpleUploadedFile(
                        "proof-1.png", b"proof-one", content_type="image/png"
                    ),
                    SimpleUploadedFile(
                        "proof-2.png", b"proof-two", content_type="image/png"
                    ),
                ],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.json())
        return response, TutoringResource.objects.get(pk=response.json()["id"])

    def test_instructor_submits_proof_and_manual_account_is_returned(self):
        response, resource = self._create_resource()

        self.assertEqual(resource.fee_payment_status, "PENDING")
        self.assertTrue(resource.is_instructor_confirmed)
        self.assertFalse(resource.is_student_confirmed)
        self.assertEqual(resource.files.count(), 2)
        self.assertEqual(response.json()["payment_bank"], "우리은행")
        self.assertEqual(
            response.json()["payment_account_number"], "124411-0045778"
        )
        self.assertEqual(response.json()["expected_commission_amount"], 75000)

    @override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=0)
    def test_temporary_upload_is_not_saved_twice(self):
        response, resource = self._create_resource()

        self.assertEqual(response.status_code, 201)
        self.assertFalse(bool(resource.fee_confirmation_file))
        self.assertEqual(resource.files.count(), 2)

    def test_student_cannot_create_contract(self):
        response = self.student_client.post(
            "/tutoring/resources/",
            data={
                "student": self.student.pk,
                "instructor": self.instructor.pk,
                "subject": [self.subject.number],
                "first_month_fee": 500000,
                "fee_confirmation_file": SimpleUploadedFile(
                    "proof.png", b"proof", content_type="image/png"
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TutoringResource.objects.count(), 0)

    def test_resource_list_returns_current_users_existing_review(self):
        resource = TutoringResource.objects.create(
            student=self.student,
            instructor=self.instructor,
        )
        instructor_review = InstructorReview.objects.create(
            student=self.student,
            instructor=self.instructor,
            professionalism=4,
            teaching_skill=5,
            punctuality=3,
            comment="좋은 수업",
        )
        student_review = StudentReview.objects.create(
            student=self.student,
            instructor=self.instructor,
            rating=4,
            comment="성실한 학생",
        )

        student_response = self.student_client.get("/tutoring/resources/")
        self.assertEqual(student_response.status_code, 200)
        student_item = student_response.json()["results"][0]
        self.assertEqual(student_item["id"], resource.pk)
        self.assertEqual(student_item["my_review"]["id"], instructor_review.pk)
        self.assertEqual(student_item["my_review"]["teaching_skill"], 5)

        instructor_response = self.instructor_client.get("/tutoring/resources/")
        self.assertEqual(instructor_response.status_code, 200)
        instructor_item = instructor_response.json()["results"][0]
        self.assertEqual(instructor_item["my_review"]["id"], student_review.pk)
        self.assertEqual(instructor_item["my_review"]["rating"], 4)

    def test_review_authors_can_patch_their_existing_reviews(self):
        instructor_review = InstructorReview.objects.create(
            student=self.student,
            instructor=self.instructor,
            professionalism=3,
            teaching_skill=3,
            punctuality=3,
            comment="수정 전",
        )
        student_review = StudentReview.objects.create(
            student=self.student,
            instructor=self.instructor,
            rating=3,
            comment="수정 전",
        )

        student_response = self.student_client.patch(
            f"/tutoring/reviews/instructor/{instructor_review.pk}/",
            {
                "professionalism": 5,
                "teaching_skill": 4,
                "punctuality": 5,
                "comment": "수정 후",
            },
            format="json",
        )
        self.assertEqual(student_response.status_code, 200)
        instructor_review.refresh_from_db()
        self.assertEqual(instructor_review.professionalism, 5)
        self.assertEqual(instructor_review.comment, "수정 후")

        instructor_response = self.instructor_client.patch(
            f"/tutoring/reviews/student/{student_review.pk}/",
            {"rating": 5, "comment": "수정 후"},
            format="json",
        )
        self.assertEqual(instructor_response.status_code, 200)
        student_review.refresh_from_db()
        self.assertEqual(student_review.rating, 5)
        self.assertEqual(student_review.comment, "수정 후")

    def test_resource_lookup_is_scoped_to_active_role(self):
        dual_role_student = Student.objects.create(user=self.instructor_user)
        other_user = User.objects.create_user(
            username="other_instructor",
            user_name="다른강사",
            password="password",
        )
        other_instructor = Instructor.objects.create(
            user=other_user,
            university="Other University",
        )
        instructor_resource = TutoringResource.objects.create(
            student=self.student,
            instructor=self.instructor,
        )
        student_resource = TutoringResource.objects.create(
            student=dual_role_student,
            instructor=other_instructor,
        )

        instructor_response = self.instructor_client.get(
            "/tutoring/resources/",
            HTTP_X_CLASSY_ROLE="instructor",
        )
        self.assertEqual(instructor_response.status_code, 200)
        instructor_ids = {
            item["id"] for item in instructor_response.json()["results"]
        }
        self.assertEqual(instructor_ids, {instructor_resource.pk})

        student_response = self.instructor_client.get(
            "/tutoring/resources/",
            HTTP_X_CLASSY_ROLE="student",
        )
        self.assertEqual(student_response.status_code, 200)
        student_ids = {
            item["id"] for item in student_response.json()["results"]
        }
        self.assertEqual(student_ids, {student_resource.pk})

        hidden_detail = self.instructor_client.get(
            f"/tutoring/resources/{student_resource.pk}/",
            HTTP_X_CLASSY_ROLE="instructor",
        )
        self.assertEqual(hidden_detail.status_code, 404)

    def test_toss_and_virtual_account_routes_are_disabled(self):
        self.assertEqual(
            self.instructor_client.post('/cash/webhook/toss/', {}).status_code,
            404,
        )
        self.assertEqual(
            self.instructor_client.get(
                '/tutoring/resources/1/commission-payment/'
            ).status_code,
            404,
        )
        self.assertEqual(
            self.instructor_client.post(
                '/tutoring/resources/1/commission-payment/reissue/', {}
            ).status_code,
            404,
        )

    def test_admin_approval_controls_contract_completion(self):
        _, resource = self._create_resource()
        confirm_response = self.instructor_client.post(
            f"/tutoring/resources/{resource.pk}/confirm-payment/"
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(
            confirm_response.json()["fee_payment_status"],
            "AWAITING_CONFIRMATION",
        )

        patch_response = self.instructor_client.patch(
            f"/tutoring/resources/{resource.pk}/",
            {"fee_payment_status": "PAID"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 405)

        model_admin = Mock()
        confirm_fee_payment(
            model_admin,
            Mock(),
            TutoringResource.objects.filter(pk=resource.pk),
        )
        resource.refresh_from_db()
        self.assertEqual(resource.fee_payment_status, "PAID")
        self.assertEqual(Notification.objects.count(), 2)

        student_list = self.student_client.get("/tutoring/resources/")
        self.assertEqual(student_list.status_code, 200)
        result = student_list.json()["results"][0]
        self.assertEqual(result["fee_payment_status"], "PAID")
        self.assertEqual(result["instructor_user_name"], "수동강사")
