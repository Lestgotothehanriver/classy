from django.conf import settings
from django.db import migrations, models


def create_existing_conversations(apps, schema_editor):
    Conversation = apps.get_model("support", "SupportConversation")
    Student = apps.get_model("accounts", "Student")
    Instructor = apps.get_model("accounts", "Instructor")
    for user_id in Student.objects.filter(user__is_active=True).values_list("user_id", flat=True).iterator():
        Conversation.objects.get_or_create(member_id=user_id, role="student")
    for user_id in Instructor.objects.filter(user__is_active=True).values_list("user_id", flat=True).iterator():
        Conversation.objects.get_or_create(member_id=user_id, role="instructor")


class Migration(migrations.Migration):
    dependencies = [("support", "0004_remove_supportticket_support_sup_assigne_6d4ffc_idx_and_more")]

    operations = [
        migrations.CreateModel(
            name="SupportConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("student", "학생"), ("instructor", "선생님")], max_length=20)),
                ("is_muted", models.BooleanField(default=False)),
                ("last_member_message_at", models.DateTimeField(blank=True, null=True)),
                ("last_operator_message_at", models.DateTimeField(blank=True, null=True)),
                ("last_member_read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("member", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="support_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="SupportConversationMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_kind", models.CharField(choices=[("MEMBER", "회원"), ("OPERATOR", "운영자"), ("SYSTEM", "시스템")], max_length=15)),
                ("content", models.TextField()),
                ("action_type", models.CharField(choices=[("NONE", "없음"), ("TUTORING_CHAT", "과외 채팅방"), ("SUPPORT_TICKET", "문의 티켓"), ("CASH_HISTORY", "구매 내역")], default="NONE", max_length=30)),
                ("action_target_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("action_label", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="messages", to="support.supportconversation")),
                ("sender", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="support_conversation_messages", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="supportconversation",
            constraint=models.UniqueConstraint(fields=("member", "role"), name="support_conversation_member_role_unique"),
        ),
        migrations.RunPython(create_existing_conversations, migrations.RunPython.noop),
    ]
