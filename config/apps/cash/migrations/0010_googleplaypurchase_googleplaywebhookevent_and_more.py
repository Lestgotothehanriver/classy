from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('cash', '0009_appstorewebhookevent_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='GooglePlaySyncState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, unique=True)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='GooglePlayWebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message_id', models.CharField(max_length=255, unique=True)),
                ('notification_type', models.PositiveIntegerField(blank=True, null=True)),
                ('product_id', models.CharField(blank=True, default='', max_length=100)),
                ('purchase_token_sha256', models.CharField(blank=True, default='', max_length=64)),
                ('status', models.CharField(choices=[('RECEIVED', '수신'), ('PROCESSED', '처리 완료'), ('IGNORED', '처리 대상 아님'), ('FAILED', '처리 실패')], default='RECEIVED', max_length=20)),
                ('detail', models.CharField(blank=True, default='', max_length=255)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['-received_at']},
        ),
        migrations.CreateModel(
            name='GooglePlayPurchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('purchase_token', models.TextField(unique=True)),
                ('order_id', models.CharField(blank=True, db_index=True, default='', max_length=255)),
                ('obfuscated_external_account_id', models.UUIDField(db_index=True)),
                ('purchase_state', models.CharField(default='PURCHASED', max_length=20)),
                ('acknowledgement_state', models.CharField(blank=True, default='', max_length=20)),
                ('consumption_state', models.CharField(default='NOT_CONSUMED', max_length=20)),
                ('last_verified_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('purchase_history', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='google_play_detail', to='cash.purchasehistory')),
            ],
        ),
    ]
