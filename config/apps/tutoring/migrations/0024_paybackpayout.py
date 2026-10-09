# Generated manually for the payback payout workflow.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tutoring", "0023_tutoringpost_admin_blocked_at_and_more")]
    operations = [migrations.CreateModel(name="PaybackPayout", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("amount", models.PositiveBigIntegerField()),
        ("status", models.CharField(choices=[("PENDING", "지급 대기"), ("COMPLETED", "지급 완료"), ("FAILED", "지급 실패")], default="PENDING", max_length=20)),
        ("payment_reference", models.CharField(blank=True, max_length=120)),
        ("failure_reason", models.TextField(blank=True)),
        ("processed_at", models.DateTimeField(blank=True, null=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("registration", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="payback_payout", to="tutoring.tutoringregistration")),
    ])]
