from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('notification', '0002_devicetoken_is_chat_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicetoken',
            name='active_role',
            field=models.CharField(
                blank=True,
                choices=[('student', '학생'), ('instructor', '선생님')],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name='devicetoken',
            index=models.Index(fields=['is_active', 'active_role'], name='notificatio_is_acti_2dd9e3_idx'),
        ),
        migrations.CreateModel(
            name='MarketingPushTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_marketing_push_templates', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name', 'id']},
        ),
        migrations.CreateModel(
            name='MarketingPushCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_role', models.CharField(choices=[('student', '학생'), ('instructor', '선생님'), ('all', '전체')], default='all', max_length=20)),
                ('title', models.CharField(max_length=200)),
                ('body', models.TextField()),
                ('scheduled_at', models.DateTimeField(db_index=True)),
                ('push_only', models.BooleanField(default=True)),
                ('status', models.CharField(choices=[('SCHEDULED', '예약됨'), ('SENDING', '발송 중'), ('COMPLETED', '완료'), ('FAILED', '실패'), ('CANCELLED', '취소됨')], db_index=True, default='SCHEDULED', max_length=16)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('recipient_count', models.PositiveIntegerField(default=0)),
                ('token_count', models.PositiveIntegerField(default=0)),
                ('success_count', models.PositiveIntegerField(default=0)),
                ('failure_count', models.PositiveIntegerField(default=0)),
                ('failure_detail', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_marketing_push_campaigns', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-scheduled_at', '-id']},
        ),
        migrations.AddIndex(
            model_name='marketingpushcampaign',
            index=models.Index(fields=['status', 'scheduled_at'], name='notificatio_status_96a662_idx'),
        ),
    ]
