# Generated for 판매 중지/재개 (suspended_at) 기능

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lecture", "0006_lecture_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="lecture",
            name="suspended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
