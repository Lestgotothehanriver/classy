from django.db import migrations, models


def mark_existing_submissions_finalized(apps, schema_editor):
    apps.get_model("tutoring", "TutoringSubmission").objects.update(
        is_finalized=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0026_commissioninvoice_promotion_benefit"),
    ]

    operations = [
        migrations.AddField(
            model_name="tutoringregistration",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="tutoringsubmission",
            name="is_finalized",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            mark_existing_submissions_finalized,
            migrations.RunPython.noop,
        ),
    ]
