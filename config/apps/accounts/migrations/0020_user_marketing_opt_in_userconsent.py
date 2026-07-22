import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0019_alter_phoneverification_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="marketing_opt_in",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="UserConsent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "doc_type",
                    models.CharField(
                        choices=[
                            ("terms", "이용약관"),
                            ("privacy", "개인정보처리방침"),
                            ("marketing", "마케팅 수신"),
                        ],
                        max_length=20,
                    ),
                ),
                ("version", models.CharField(blank=True, max_length=20)),
                ("agreed", models.BooleanField(default=True)),
                ("agreed_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-agreed_at"],
            },
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["user", "doc_type"], name="accounts_us_user_id_doc_idx"),
        ),
    ]
