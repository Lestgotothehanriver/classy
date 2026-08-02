import config.apps.accounts.uploads
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0021_phoneverification_purpose_used_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="profile_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=config.apps.accounts.uploads.profile_image_upload_to,
            ),
        ),
    ]
