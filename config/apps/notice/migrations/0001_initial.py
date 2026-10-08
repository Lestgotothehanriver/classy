from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Notice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("summary", models.CharField(max_length=300)),
                ("content", models.TextField()),
                ("banner_image", models.ImageField(blank=True, null=True, upload_to="notices/banners/")),
                ("status", models.CharField(choices=[("DRAFT", "초안"), ("PUBLISHED", "게시"), ("UNPUBLISHED", "게시 중단")], db_index=True, default="DRAFT", max_length=16)),
                ("publish_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("exposure_type", models.CharField(choices=[("LIST", "목록만"), ("HOME_BANNER", "홈 배너 · 앱 공지 모달")], db_index=True, default="LIST", max_length=20)),
                ("exposure_ends_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("banner_order", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_notices", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_notices", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-publish_at", "-created_at"]},
        ),
        migrations.AddIndex(model_name="notice", index=models.Index(fields=["status", "publish_at"], name="notice_stat_publish_idx")),
        migrations.AddIndex(model_name="notice", index=models.Index(fields=["exposure_type", "exposure_ends_at"], name="notice_expo_ends_idx")),
    ]
