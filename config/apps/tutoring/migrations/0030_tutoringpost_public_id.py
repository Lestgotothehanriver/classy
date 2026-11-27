import uuid

from django.db import migrations, models


def backfill_tutoring_post_public_ids(apps, schema_editor):
    post_model = apps.get_model("tutoring", "TutoringPost")
    for post in post_model.objects.filter(public_id__isnull=True).iterator():
        post.public_id = uuid.uuid4()
        post.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("tutoring", "0029_tutoringpost_student_detail_length")]

    operations = [
        migrations.AddField(
            model_name="tutoringpost",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_tutoring_post_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tutoringpost",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
