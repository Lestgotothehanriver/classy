from base64 import b64decode

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from config.apps.accounts.models import User

from .models import Report, ReportReasonChoices


class ReportCreateAPITests(APITestCase):
    def setUp(self):
        self.reporter = User.objects.create_user(
            username="reporter",
            user_name="reporter",
            password="pass1234",
        )
        self.target = User.objects.create_user(
            username="report_target",
            user_name="report_target",
            password="pass1234",
        )
        self.client.force_authenticate(self.reporter)

    def test_create_accepts_legacy_app_reason_codes(self):
        response = self.client.post(
            "/report/create/",
            {
                "reported_user": self.target.pk,
                "choices": ["PROFANITY", "UNREPORTED_CLASS"],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        report = Report.objects.get()
        self.assertCountEqual(
            report.choices.values_list("content", flat=True),
            [
                ReportReasonChoices.ABUSIVE_LANGUAGE,
                ReportReasonChoices.UNREPORTED_CLASS_COMPLETION,
            ],
        )

    def test_create_accepts_current_reason_codes(self):
        response = self.client.post(
            "/report/create/",
            {
                "reported_user": self.target.pk,
                "choices": [ReportReasonChoices.INAPPROPRIATE_CONTENT],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)

    def test_create_accepts_three_evidence_images(self):
        """신고는 증거 이미지를 최대 세 장까지 함께 저장한다."""
        images = [
            SimpleUploadedFile(
                f"evidence-{index}.png",
                b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9JX1wAAAAASUVORK5CYII="
                ),
                content_type="image/png",
            )
            for index in range(3)
        ]

        response = self.client.post(
            "/report/create/",
            {
                "reported_user": self.target.pk,
                "choices": [ReportReasonChoices.INAPPROPRIATE_CONTENT],
                "evidence_images": images,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Report.objects.get().attachments.count(), 3)

    def test_create_rejects_description_over_500_characters(self):
        """상세 내용은 앱과 동일하게 500자 이하만 받는다."""
        response = self.client.post(
            "/report/create/",
            {
                "reported_user": self.target.pk,
                "choices": [ReportReasonChoices.INAPPROPRIATE_CONTENT],
                "description": "가" * 501,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("description", response.data)
