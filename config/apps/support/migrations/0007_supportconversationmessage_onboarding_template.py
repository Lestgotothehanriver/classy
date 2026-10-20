from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0006_supportconversation_last_operator_read_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportconversationmessage",
            name="onboarding_template_key",
            field=models.CharField(
                blank=True,
                choices=[
                    ("student_welcome", "학생 가입 안내"),
                    ("student_payback", "학생 페이백 안내"),
                    ("instructor_welcome", "선생님 가입 안내"),
                ],
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="supportconversationmessage",
            constraint=models.UniqueConstraint(
                condition=Q(("onboarding_template_key__isnull", False)),
                fields=("conversation", "onboarding_template_key"),
                name="support_conversation_onboarding_template_unique",
            ),
        ),
    ]
