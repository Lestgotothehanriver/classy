from django.db import migrations


def recount_confirmed_tutoring_uses(apps, schema_editor):
    """입금 확인이 끝난 과외 성사 건만 프로모션 사용으로 집계한다."""
    InstructorPromotionBenefit = apps.get_model(
        "promotions",
        "InstructorPromotionBenefit",
    )
    CommissionInvoice = apps.get_model("tutoring", "CommissionInvoice")

    for benefit in InstructorPromotionBenefit.objects.iterator():
        invoices = CommissionInvoice.objects.filter(
            promotion_benefit_id=benefit.pk,
            invoice_type="INITIAL",
            status="PAID",
        ).order_by("paid_at", "id")
        CommissionInvoice.objects.filter(
            promotion_benefit_id=benefit.pk,
            invoice_type="INITIAL",
        ).exclude(status="PAID").update(promotion_usage_number=None)
        for usage_number, invoice_id in enumerate(
            invoices.values_list("pk", flat=True),
            start=1,
        ):
            CommissionInvoice.objects.filter(pk=invoice_id).update(
                promotion_usage_number=usage_number,
            )
        InstructorPromotionBenefit.objects.filter(pk=benefit.pk).update(
            used_tutoring_registration_count=invoices.count(),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("promotions", "0001_initial"),
        ("tutoring", "0026_commissioninvoice_promotion_benefit"),
    ]

    operations = [
        migrations.RunPython(recount_confirmed_tutoring_uses, migrations.RunPython.noop),
    ]
