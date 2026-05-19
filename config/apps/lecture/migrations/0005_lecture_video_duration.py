from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lecture", "0004_lecture_deleted_at_lecture_is_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="lecture",
            name="video_duration",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
