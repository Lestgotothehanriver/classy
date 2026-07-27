from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0020_user_marketing_opt_in_userconsent"),
    ]

    operations = [
        migrations.AddField(
            model_name="phoneverification",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("GENERAL", "일반 인증"),
                    ("PASSWORD_RESET", "비밀번호 재설정"),
                    ("PHONE_CHANGE", "전화번호 변경"),
                ],
                default="GENERAL",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="phoneverification",
            name="used_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
