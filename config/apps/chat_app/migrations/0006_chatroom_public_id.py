import uuid

from django.db import migrations, models


def backfill_chat_room_public_ids(apps, schema_editor):
    room_model = apps.get_model("chat_app", "ChatRoom")
    for room in room_model.objects.filter(public_id__isnull=True).iterator():
        room.public_id = uuid.uuid4()
        room.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("chat_app", "0005_remove_blockeduser_unique_block_delete_blockeduser")]

    operations = [
        migrations.AddField(
            model_name="chatroom",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_chat_room_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="chatroom",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
