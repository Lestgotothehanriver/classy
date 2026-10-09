# Generated manually for the support-ticket v1 rollout.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requester_name", models.CharField(blank=True, max_length=80)),
                ("requester_role", models.CharField(blank=True, max_length=20)),
                ("ticket_type", models.CharField(choices=[("NAME_CHANGE", "이름 변경"), ("CASH_PAYMENT", "캐시·결제"), ("TUTORING_FEE", "성사 수수료"), ("PAYBACK", "페이백"), ("VERIFICATION_PROFILE", "인증·프로필"), ("LEGACY", "기존 문의")], db_index=True, max_length=30)),
                ("status", models.CharField(choices=[("RECEIVED", "접수"), ("IN_PROGRESS", "처리 중"), ("WAITING_FOR_USER", "추가 정보 필요"), ("RESOLVED", "해결"), ("CLOSED", "종결")], db_index=True, default="RECEIVED", max_length=30)),
                ("title", models.CharField(max_length=255)),
                ("related_kind", models.CharField(blank=True, choices=[("PURCHASE", "구매 내역"), ("TUTORING_REGISTRATION", "성사등록"), ("INSTRUCTOR_VERIFICATION", "학력 인증")], max_length=40)),
                ("related_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("requested_last_name", models.CharField(blank=True, max_length=150)),
                ("requested_first_name", models.CharField(blank=True, max_length=150)),
                ("name_change_reason", models.TextField(blank=True)),
                ("last_admin_message_at", models.DateTimeField(blank=True, null=True)),
                ("last_user_message_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("requester", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_tickets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="SupportMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_name", models.CharField(blank=True, max_length=80)),
                ("sender_kind", models.CharField(choices=[("USER", "사용자"), ("ADMIN", "운영자"), ("SYSTEM", "시스템")], max_length=15)),
                ("content", models.TextField()),
                ("is_internal", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("sender", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="support.supportticket")),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.CreateModel(
            name="SupportEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_name", models.CharField(blank=True, max_length=80)),
                ("event_type", models.CharField(db_index=True, max_length=80)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="support.supportticket")),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.CreateModel(
            name="SupportAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="support/%Y/%m/")),
                ("original_name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attachments", to="support.supportmessage")),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="support.supportticket")),
            ],
        ),
        migrations.AddIndex(model_name="supportticket", index=models.Index(fields=["status", "ticket_type", "updated_at"], name="support_sup_status_84c7ee_idx")),
        migrations.AddIndex(model_name="supportticket", index=models.Index(fields=["assigned_to", "status", "updated_at"], name="support_sup_assigne_1d6bf0_idx")),
        migrations.AddIndex(model_name="supportticket", index=models.Index(fields=["related_kind", "related_id"], name="support_sup_related_1869ea_idx")),
    ]
