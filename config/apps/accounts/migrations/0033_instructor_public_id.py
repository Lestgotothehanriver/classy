import uuid

from django.db import migrations, models


def backfill_instructor_public_ids(apps, schema_editor):
    instructor_model = apps.get_model("accounts", "Instructor")
    for instructor in instructor_model.objects.filter(public_id__isnull=True).iterator():
        instructor.public_id = uuid.uuid4()
        instructor.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0032_limit_instructor_instruction")]

    operations = [
        migrations.AddField(
            model_name="instructor",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_instructor_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="instructor",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
