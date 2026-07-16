# 대여 만료일(expiration_date) 저장 구조 도입 + 기존 데이터 백필

from datetime import timedelta

from django.db import migrations, models


def backfill_expiration_date(apps, schema_editor):
    """기존 대여 이력에 created_at + lecture.rental_period(일)로 만료일을 채운다."""
    LectureRentalHistory = apps.get_model("cash", "LectureRentalHistory")
    for rental in LectureRentalHistory.objects.select_related("lecture").iterator():
        if rental.expiration_date is None and rental.created_at is not None:
            rental.expiration_date = rental.created_at + timedelta(
                days=rental.lecture.rental_period
            )
            rental.save(update_fields=["expiration_date"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cash", "0005_coupon"),
    ]

    operations = [
        migrations.AddField(
            model_name="lecturerentalhistory",
            name="expiration_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_expiration_date, noop_reverse),
    ]
