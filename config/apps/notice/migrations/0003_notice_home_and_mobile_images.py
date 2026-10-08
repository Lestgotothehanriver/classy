from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notice", "0002_remove_emergency_modal")]

    operations = [
        migrations.RenameField(
            model_name="notice",
            old_name="banner_image",
            new_name="home_banner_image",
        ),
        migrations.AlterField(
            model_name="notice",
            name="home_banner_image",
            field=models.ImageField(
                blank=True, null=True, upload_to="notices/home_banners/"
            ),
        ),
        migrations.AddField(
            model_name="notice",
            name="mobile_image",
            field=models.ImageField(blank=True, null=True, upload_to="notices/mobile/"),
        ),
        migrations.AlterField(
            model_name="notice",
            name="exposure_type",
            field=models.CharField(
                choices=[("LIST", "목록만"), ("HOME_BANNER", "홈 배너 · 앱 공지")],
                db_index=True,
                default="LIST",
                max_length=20,
            ),
        ),
    ]
