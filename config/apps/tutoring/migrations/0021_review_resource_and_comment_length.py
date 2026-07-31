import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0020_remove_tutoringresource_payback_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorreview",
            name="resource",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="instructor_review",
                to="tutoring.tutoringresource",
            ),
        ),
        migrations.AddField(
            model_name="studentreview",
            name="resource",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="student_review",
                to="tutoring.tutoringresource",
            ),
        ),
        migrations.AlterField(
            model_name="instructorreview",
            name="comment",
            field=models.TextField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="studentreview",
            name="comment",
            field=models.TextField(blank=True, max_length=500),
        ),
    ]
