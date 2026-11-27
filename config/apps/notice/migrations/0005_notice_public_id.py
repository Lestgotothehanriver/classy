import uuid

from django.db import migrations, models


def backfill_notice_public_ids(apps, schema_editor):
    notice_model = apps.get_model("notice", "Notice")
    for notice in notice_model.objects.filter(public_id__isnull=True).iterator():
        notice.public_id = uuid.uuid4()
        notice.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("notice", "0004_rename_notice_stat_publish_idx_notice_noti_status_b46a62_idx_and_more")]

    operations = [
        migrations.AddField(
            model_name="notice",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_notice_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notice",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
