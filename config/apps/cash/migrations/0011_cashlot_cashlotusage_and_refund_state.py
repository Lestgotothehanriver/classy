from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_legacy_lots(apps, schema_editor):
    """Keep existing balances spendable without inferring historic package use."""
    User = apps.get_model('accounts', 'User')
    CashLot = apps.get_model('cash', 'CashLot')
    for user in User.objects.filter(cash__gt=0).iterator():
        CashLot.objects.create(
            user_id=user.pk,
            source='legacy',
            original_cash=user.cash,
            available_cash=user.cash,
            status='active',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0026_email_snapshots'),
        ('cash', '0010_googleplaypurchase_googleplaywebhookevent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchasehistory',
            name='refund_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='purchasehistory',
            name='refund_status',
            field=models.CharField(default='not_requested', max_length=32),
        ),
        migrations.CreateModel(
            name='CashLot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('paid', '유상 충전'), ('coupon', '쿠폰'), ('promotion', '프로모션'), ('legacy', '기존 잔액')], max_length=20)),
                ('original_cash', models.PositiveIntegerField()),
                ('available_cash', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('active', '사용 가능'), ('used', '전액 사용'), ('refunded', '환불됨')], default='active', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('purchase_history', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cash_lot', to='cash.purchasehistory')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cash_lots', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CashLotUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('used_cash', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cash_lot', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='usages', to='cash.cashlot')),
                ('rental', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cash_lot_usages', to='cash.lecturerentalhistory')),
            ],
        ),
        migrations.AddIndex(
            model_name='cashlot',
            index=models.Index(fields=['user', 'source', 'created_at'], name='cash_lot_user_source_created'),
        ),
        migrations.AddConstraint(
            model_name='cashlot',
            constraint=models.CheckConstraint(condition=models.Q(('available_cash__lte', models.F('original_cash'))), name='cash_lot_available_lte_original'),
        ),
        migrations.RunPython(create_legacy_lots, migrations.RunPython.noop),
    ]
