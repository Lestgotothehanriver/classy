"""기존 활성 성사등록에 누락된 페이백 지급 대기를 보정합니다."""

from django.db import migrations


PAYBACK_RATE_BPS = 50


def create_missing_paybacks(apps, schema_editor):
    """ACTIVE 상태이며 첫 달 수업료가 확정된 등록에만 지급 대기를 생성합니다."""
    Registration = apps.get_model("tutoring", "TutoringRegistration")
    Payout = apps.get_model("tutoring", "PaybackPayout")
    registrations = Registration.objects.filter(
        contract_status="ACTIVE",
        confirmed_first_month_fee__isnull=False,
    ).iterator()
    for registration in registrations:
        Payout.objects.get_or_create(
            registration_id=registration.pk,
            defaults={
                "amount": registration.confirmed_first_month_fee * PAYBACK_RATE_BPS // 10_000,
                "status": "PENDING",
            },
        )


class Migration(migrations.Migration):
    dependencies = [("tutoring", "0024_paybackpayout")]

    operations = [
        migrations.RunPython(create_missing_paybacks, migrations.RunPython.noop),
    ]
