from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("promotions", "0001_initial"),
        ("tutoring", "0025_backfill_active_payback_payouts"),
    ]

    operations = [
        migrations.AddField(
            model_name="commissioninvoice",
            name="promotion_benefit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commission_invoices",
                to="promotions.instructorpromotionbenefit",
            ),
        ),
        migrations.AddField(
            model_name="commissioninvoice",
            name="promotion_usage_number",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
