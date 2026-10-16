from django.db import migrations, models
import django.db.models.deletion


def backfill_settlement_snapshot(apps, schema_editor):
    SettlementRecord = apps.get_model("cash", "SettlementRecord")
    for settlement in SettlementRecord.objects.all().iterator():
        fee = settlement.amount * 2000 // 10000
        SettlementRecord.objects.filter(pk=settlement.pk).update(
            platform_fee_rate_bps=2000,
            platform_fee_amount=fee,
            payout_amount=settlement.amount - fee,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cash", "0012_lecturerentalhistory_is_sandbox"),
        ("promotions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="settlementrecord",
            name="platform_fee_rate_bps",
            field=models.PositiveIntegerField(default=2000),
        ),
        migrations.AddField(
            model_name="settlementrecord",
            name="platform_fee_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="settlementrecord",
            name="payout_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="settlementrecord",
            name="promotion_benefit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="settlement_records",
                to="promotions.instructorpromotionbenefit",
            ),
        ),
        migrations.RunPython(backfill_settlement_snapshot, migrations.RunPython.noop),
    ]
