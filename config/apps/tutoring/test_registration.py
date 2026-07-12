from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from config.apps.accounts.models import Instructor, Student, User
from config.apps.chat_app.models import ChatRoom

from .models import (
    CommissionInvoice,
    StudentPaybackAccount,
    TossWebhookEvent,
    TutoringPost,
    TutoringRegistration,
    TutoringSubmission,
    VirtualAccountPayment,
)


@override_settings(TOSS_PAYMENTS_SECRET_KEY="test_sk")
class TutoringRegistrationFlowTest(APITestCase):
    def setUp(self):
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
            user=self.instructor_user, university="Classy University"
        )
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
        self.url = f"/tutoring/resources/chatrooms/{self.room.pk}/my-registration/"

    def student_payload(self, fee=500000, class_type="REGULAR"):
        return {
            "subject": "수학",
            "startDate": "2026-07-20",
            "classType": class_type,
            "firstMonthFee": fee,
            "paybackAccount": {
                "bankCode": "020",
                "accountNumber": "123-456-789012",
                "accountHolder": "홍길동",
            },
        }

    def instructor_payload(self, fee=500000, class_type="REGULAR"):
        return {
            "subject": "수학",
            "startDate": "2026-07-20",
            "classType": class_type,
            "firstMonthFee": fee,
        }

    def toss_response(self, payment_key="payment-key-1"):
        response = Mock(ok=True)
        response.json.return_value = {
            "paymentKey": payment_key,
            "orderId": "ignored-response-order-id",
            "status": "WAITING_FOR_DEPOSIT",
            "secret": "webhook-secret",
            "virtualAccount": {
                "bankCode": "20",
                "accountNumber": "12345678901234",
                "customerName": "등록강사",
                "dueDate": "2026-07-30T23:59:59+09:00",
            },
        }
        return response

    def test_student_first_then_matching_instructor_issues_once(self):
        student_response = self.student_client.put(
            self.url, self.student_payload(), format="json"
        )
        self.assertEqual(student_response.status_code, 200)
        self.assertIsNone(student_response.json()["payment"])
        self.assertEqual(
            student_response.json()["registration"]["attributeValidationStatus"],
            "UNCHECKED",
        )

        account = StudentPaybackAccount.objects.get()
        self.assertNotIn("123456789012", account.encrypted_account_number)

        lookup = self.instructor_client.get(
            f"/tutoring/resources/chatrooms/{self.room.pk}/"
        )
        self.assertEqual(lookup.status_code, 200)
        self.assertTrue(lookup.json()["counterpartySubmission"]["submitted"])
        self.assertNotIn("classType", lookup.json()["counterpartySubmission"])
        self.assertNotIn("firstMonthFee", lookup.json()["counterpartySubmission"])

        with patch(
            "config.apps.tutoring.registration_services.requests.post",
            return_value=self.toss_response(),
        ) as toss_post:
            instructor_response = self.instructor_client.put(
                self.url, self.instructor_payload(), format="json"
            )
        self.assertEqual(instructor_response.status_code, 200)
        body = instructor_response.json()
        self.assertEqual(
            body["registration"]["attributeValidationStatus"], "MATCHED"
        )
        self.assertEqual(body["payment"]["amount"], 75000)
        self.assertEqual(body["payment"]["status"], "WAITING_FOR_DEPOSIT")
        self.assertEqual(toss_post.call_args.kwargs["json"]["amount"], 75000)

        with patch(
            "config.apps.tutoring.registration_services.requests.post"
        ) as retry_post:
            retry = self.instructor_client.put(
                self.url, self.instructor_payload(), format="json"
            )
        self.assertEqual(retry.status_code, 200)
        retry_post.assert_not_called()
        self.assertEqual(CommissionInvoice.objects.count(), 1)
        self.assertEqual(VirtualAccountPayment.objects.count(), 1)

    def test_instructor_first_then_mismatching_student_keeps_payment(self):
        with patch(
            "config.apps.tutoring.registration_services.requests.post",
            return_value=self.toss_response(),
        ):
            instructor_response = self.instructor_client.put(
                self.url, self.instructor_payload(fee=400000), format="json"
            )
        self.assertEqual(
            instructor_response.json()["registration"]["attributeValidationStatus"],
            "UNCHECKED",
        )
        self.assertEqual(instructor_response.json()["payment"]["amount"], 60000)

        student_response = self.student_client.put(
            self.url, self.student_payload(fee=500000), format="json"
        )
        body = student_response.json()
        self.assertEqual(body["registration"]["attributeValidationStatus"], "MISMATCHED")
        self.assertEqual(body["registration"]["mismatchedFields"], ["firstMonthFee"])
        self.assertEqual(body["payment"]["amount"], 60000)
        self.assertEqual(VirtualAccountPayment.objects.count(), 1)

    def test_short_term_uses_seven_percent(self):
        with patch(
            "config.apps.tutoring.registration_services.requests.post",
            return_value=self.toss_response(),
        ):
            response = self.instructor_client.put(
                self.url,
                self.instructor_payload(fee=300000, class_type="SHORT_TERM"),
                format="json",
            )
        self.assertEqual(response.json()["payment"]["amount"], 21000)
        invoice = CommissionInvoice.objects.get()
        self.assertEqual(invoice.commission_rate_bps, 700)

    @override_settings(TOSS_PAYMENTS_SECRET_KEY="")
    def test_toss_failure_does_not_roll_back_contract_submission(self):
        response = self.instructor_client.put(
            self.url, self.instructor_payload(), format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment"]["status"], "FAILED")
        self.assertIn("paymentError", response.json())
        self.assertEqual(TutoringRegistration.objects.count(), 1)
        self.assertEqual(TutoringSubmission.objects.count(), 1)
        self.assertEqual(CommissionInvoice.objects.get().status, "FAILED")

    def test_webhook_is_verified_and_idempotent(self):
        with patch(
            "config.apps.tutoring.registration_services.requests.post",
            return_value=self.toss_response(),
        ):
            self.instructor_client.put(
                self.url, self.instructor_payload(), format="json"
            )
        payment = VirtualAccountPayment.objects.get()
        event = {
            "orderId": payment.order_id,
            "transactionKey": "transaction-1",
            "status": "DONE",
            "secret": "webhook-secret",
        }
        webhook_client = APIClient()
        response = webhook_client.post("/cash/webhook/toss/", event, format="json")
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        payment.invoice.refresh_from_db()
        self.assertEqual(payment.fee_payment_status, "DONE")
        self.assertEqual(payment.invoice.status, "PAID")
        self.assertIsNotNone(payment.invoice.paid_at)

        duplicate = webhook_client.post("/cash/webhook/toss/", event, format="json")
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertEqual(TossWebhookEvent.objects.count(), 1)

        invalid = {**event, "transactionKey": "transaction-2", "secret": "bad"}
        invalid_response = webhook_client.post(
            "/cash/webhook/toss/", invalid, format="json"
        )
        self.assertEqual(invalid_response.status_code, 403)
        self.assertEqual(TossWebhookEvent.objects.count(), 1)

    def test_failed_payment_can_be_reissued_on_same_invoice(self):
        with override_settings(TOSS_PAYMENTS_SECRET_KEY=""):
            self.instructor_client.put(
                self.url, self.instructor_payload(), format="json"
            )
        registration = TutoringRegistration.objects.get()
        reissue_url = (
            f"/tutoring/resources/{registration.pk}/commission-payment/reissue/"
        )
        with patch(
            "config.apps.tutoring.registration_services.requests.post",
            return_value=self.toss_response(payment_key="payment-key-2"),
        ):
            response = self.instructor_client.post(reissue_url, {}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "WAITING_FOR_DEPOSIT")
        self.assertEqual(CommissionInvoice.objects.count(), 1)
        self.assertEqual(VirtualAccountPayment.objects.count(), 2)

    def test_outsider_cannot_read_or_write_registration(self):
        outsider_client = APIClient()
        outsider_client.force_authenticate(self.outsider)
        read = outsider_client.get(
            f"/tutoring/resources/chatrooms/{self.room.pk}/"
        )
        write = outsider_client.put(
            self.url, self.instructor_payload(), format="json"
        )
        self.assertEqual(read.status_code, 403)
        self.assertEqual(write.status_code, 403)
