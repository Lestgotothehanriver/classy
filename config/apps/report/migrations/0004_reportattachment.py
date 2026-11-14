import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("report", "0003_report_content_type_report_description_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportAttachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image", models.ImageField(upload_to="reports/evidence/")),
                ("position", models.PositiveSmallIntegerField(default=0)),
                (
                    "report",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="report.report",
                    ),
                ),
            ],
            options={"ordering": ["position", "id"]},
        ),
    ]
