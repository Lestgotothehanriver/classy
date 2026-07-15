import tempfile
from unittest.mock import Mock

from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from config.apps.accounts.models import Instructor, Student, Subject, User
from config.apps.chat_app.models import ChatRoom
from config.apps.notification.models import Notification
from config.apps.tutoring.admin import (
    TutoringRegistrationAdmin,
    TutoringResourceAdmin,
    confirm_fee_payment,
)
from config.apps.tutoring.registration_services import decrypt_account_number

from .models import (
    CommissionInvoice,
    StudentPaybackAccount,
    TutoringPost,
    TutoringRegistration,
    TutoringResource,
    TutoringSubmission,
)


class TutoringRegistrationFlowTest(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            FILE_UPLOAD_MAX_MEMORY_SIZE=0,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.student_user = User.objects.create_user(
            username="registration_student",
            user_name="등록학생",
            password="password",
        )
        self.instructor_user = User.objects.create_user(
            username="registration_instructor",
            user_name="등록강사",
            password="password",
        )
        self.outsider = User.objects.create_user(
            username="registration_outsider",
            user_name="외부인",
            password="password",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.instructor = Instructor.objects.create(
            user=self.instructor_user,
            university="Classy University",
        )
        self.subject = Subject.objects.create(number=3)
        self.post = TutoringPost.objects.create(student=self.student, title="수학")
        self.room = ChatRoom.objects.create(
            student=self.student,
            instructor=self.instructor,
            post=self.post,
            initiated_by=self.student_user,
        )
        self.student_client = APIClient()
        self.student_client.force_authenticate(self.student_user)
        self.instructor_client = APIClient()
        self.instructor_client.force_authenticate(self.instructor_user)
        self.url = (
            f"/tutoring/resources/chatrooms/{self.room.pk}/my-registration/"
        )

    def student_payload(self, fee=500000, class_type="REGULAR"):
        return {
            "subject": "수학",
            "subjectIds": [self.subject.number],
            "startDate": "2026-07-20",
            "classType": class_type,
            "firstMonthFee": fee,
            "paybackAccount": {
                "bankCode": "우리은행",
                "accountNumber": "123-456-789012",
                "accountHolder": "홍길동",
            },
        }

    def instructor_payload(self, fee=500000, class_type="REGULAR"):
        return {
            "subject": "수학",
            "subjectIds": [str(self.subject.number)],
            "startDate": "2026-07-20",
            "classType": class_type,
            "firstMonthFee": str(fee),
            "feeConfirmationFiles": [
                SimpleUploadedFile(
                    "proof-1.jpg", b"proof-one", content_type="image/jpeg"
                ),
                SimpleUploadedFile(
                    "proof-2.jpg", b"proof-two", content_type="image/jpeg"
                ),
            ],
        }

    def test_student_first_then_matching_instructor_uses_manual_payment(self):
        student_response = self.student_client.put(
            self.url,
            self.student_payload(),
            format="json",
        )
        self.assertEqual(student_response.status_code, 200, student_response.data)
        self.assertIsNone(student_response.json()["payment"])
        self.assertEqual(
            student_response.json()["registration"]["attributeValidationStatus"],
            "UNCHECKED",
        )

        account = StudentPaybackAccount.objects.get()
        self.assertNotIn("123456789012", account.encrypted_account_number)
        self.assertEqual(
            decrypt_account_number(account.encrypted_account_number),
            "123456789012",
        )

        lookup = self.instructor_client.get(
            f"/tutoring/resources/chatrooms/{self.room.pk}/"
        )
        self.assertEqual(lookup.status_code, 200)
        self.assertTrue(lookup.json()["counterpartySubmission"]["submitted"])
        self.assertNotIn("classType", lookup.json()["counterpartySubmission"])
        self.assertNotIn("firstMonthFee", lookup.json()["counterpartySubmission"])

        instructor_response = self.instructor_client.put(
            self.url,
            self.instructor_payload(),
            format="multipart",
        )
        self.assertEqual(
            instructor_response.status_code,
            200,
            instructor_response.data,
        )
        body = instructor_response.json()
        self.assertEqual(
            body["registration"]["attributeValidationStatus"], "MATCHED"
        )
        self.assertEqual(body["payment"]["amount"], 75000)
        self.assertEqual(body["payment"]["status"], "PAYMENT_PENDING")
        self.assertNotIn("virtualAccount", body["payment"])
        self.assertEqual(CommissionInvoice.objects.count(), 1)
        self.assertEqual(TutoringResource.objects.get().files.count(), 2)

    def test_short_term_uses_seven_percent(self):
        response = self.instructor_client.put(
            self.url,
            self.instructor_payload(fee=300000, class_type="SHORT_TERM"),
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.json()["payment"]["amount"], 21000)
        self.assertEqual(CommissionInvoice.objects.get().commission_rate_bps, 700)

    def test_mismatch_is_reported_without_exposing_counterparty_values(self):
        instructor_response = self.instructor_client.put(
            self.url,
            self.instructor_payload(fee=400000),
            format="multipart",
        )
        self.assertEqual(instructor_response.status_code, 200)

        student_response = self.student_client.put(
            self.url,
            self.student_payload(fee=500000),
            format="json",
        )
        body = student_response.json()
        self.assertEqual(
            body["registration"]["attributeValidationStatus"], "MISMATCHED"
        )
        self.assertEqual(
            body["registration"]["mismatchedFields"], ["firstMonthFee"]
        )
        self.assertEqual(
            body["registration"]["counterpartySubmission"], {"submitted": True}
        )
        self.assertEqual(body["payment"]["amount"], 60000)

    def test_contract_activates_only_after_match_and_deposit_confirmation(self):
        self.student_client.put(self.url, self.student_payload(), format="json")
        self.instructor_client.put(
            self.url,
            self.instructor_payload(),
            format="multipart",
        )
        registration = TutoringRegistration.objects.get()
        self.assertEqual(registration.contract_status, "REGISTERED")

        resource = TutoringResource.objects.get()
        model_admin = Mock()
        confirm_fee_payment(
            model_admin,
            Mock(),
            TutoringResource.objects.filter(pk=resource.pk),
        )
        registration.refresh_from_db()
        resource.refresh_from_db()
        self.assertEqual(resource.fee_payment_status, "PAID")
        self.assertEqual(CommissionInvoice.objects.get().status, "PAID")
        self.assertEqual(registration.contract_status, "ACTIVE")
        self.assertEqual(Notification.objects.count(), 2)

    def test_admin_exposes_submissions_payback_and_direct_payment_edit(self):
        self.student_client.put(self.url, self.student_payload(), format="json")
        self.instructor_client.put(
            self.url,
            self.instructor_payload(),
            format="multipart",
        )
        registration = TutoringRegistration.objects.get()
        resource = TutoringResource.objects.get()

        registration_admin = TutoringRegistrationAdmin(
            TutoringRegistration,
            admin.site,
        )
        self.assertEqual(
            registration_admin.get_student_class_type(registration),
            "정규 수업",
        )
        self.assertEqual(registration_admin.get_student_fee(registration), "500,000원")
        self.assertEqual(
            registration_admin.get_instructor_class_type(registration),
            "정규 수업",
        )
        self.assertEqual(
            registration_admin.get_instructor_fee(registration),
            "500,000원",
        )

        resource_admin = TutoringResourceAdmin(TutoringResource, admin.site)
        self.assertEqual(resource_admin.get_payback_bank(resource), "우리은행")
        self.assertEqual(
            resource_admin.get_payback_account_number(resource),
            "123456789012",
        )
        self.assertEqual(resource_admin.get_payback_account_holder(resource), "홍길동")

        resource.fee_payment_status = "PAID"
        resource_admin.save_model(Mock(), resource, Mock(), change=True)
        registration.refresh_from_db()
        self.assertEqual(CommissionInvoice.objects.get().status, "PAID")
        self.assertEqual(registration.contract_status, "ACTIVE")

    def test_paid_mismatch_activates_after_corrected_submission(self):
        self.instructor_client.put(
            self.url,
            self.instructor_payload(fee=400000),
            format="multipart",
        )
        self.student_client.put(
            self.url,
            self.student_payload(fee=500000),
            format="json",
        )
        resource = TutoringResource.objects.get()
        confirm_fee_payment(
            Mock(),
            Mock(),
            TutoringResource.objects.filter(pk=resource.pk),
        )

        registration = TutoringRegistration.objects.get()
        registration.refresh_from_db()
        self.assertEqual(registration.contract_status, "REGISTERED")
        self.assertEqual(Notification.objects.count(), 0)

        corrected = self.student_client.put(
            self.url,
            self.student_payload(fee=400000),
            format="json",
        )
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(
            corrected.json()["registration"]["contractStatus"], "ACTIVE"
        )
        self.assertEqual(Notification.objects.count(), 2)

    def test_outsider_cannot_read_or_submit_registration(self):
        outsider_client = APIClient()
        outsider_client.force_authenticate(self.outsider)
        read = outsider_client.get(
            f"/tutoring/resources/chatrooms/{self.room.pk}/"
        )
        write = outsider_client.put(
            self.url,
            self.student_payload(),
            format="json",
        )
        self.assertEqual(read.status_code, 403)
        self.assertEqual(write.status_code, 403)
        self.assertEqual(TutoringSubmission.objects.count(), 0)
