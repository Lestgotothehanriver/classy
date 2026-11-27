import uuid

from django.db import migrations, models


def backfill_public_ids(apps, schema_editor):
    for model_name in ("Lecture", "Comment"):
        model = apps.get_model("lecture", model_name)
        for row in model.objects.filter(public_id__isnull=True).iterator():
            row.public_id = uuid.uuid4()
            row.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("lecture", "0012_comment_reply_to")]

    operations = [
        migrations.AddField(
            model_name="lecture",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="comment",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="lecture",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="comment",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
