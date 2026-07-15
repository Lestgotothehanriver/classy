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
