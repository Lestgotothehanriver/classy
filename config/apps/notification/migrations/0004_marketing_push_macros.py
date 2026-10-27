from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('notification', '0003_marketing_push_campaigns'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketingPushMacro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('target_role', models.CharField(choices=[('student', '학생'), ('instructor', '선생님'), ('all', '전체')], default='all', max_length=20)),
                ('title', models.CharField(max_length=200)),
                ('body', models.TextField()),
                ('push_only', models.BooleanField(default=True)),
                ('recurrence', models.CharField(choices=[('DAILY', '매일'), ('WEEKLY', '매주'), ('MONTHLY', '매월')], max_length=16)),
                ('scheduled_time', models.TimeField(help_text='Asia/Seoul 기준 실행 시각')),
                ('weekday', models.PositiveSmallIntegerField(blank=True, help_text='매주 발송의 요일입니다. 월요일은 0, 일요일은 6입니다.', null=True)),
                ('day_of_month', models.PositiveSmallIntegerField(blank=True, help_text='매월 발송의 일자입니다. 해당 월에 없으면 말일에 발송합니다.', null=True)),
                ('next_scheduled_at', models.DateTimeField(db_index=True)),
                ('last_dispatched_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_marketing_push_macros', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name', 'id']},
        ),
        migrations.AddField(
            model_name='marketingpushcampaign',
            name='macro',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='campaigns', to='notification.marketingpushmacro'),
        ),
        migrations.AddIndex(
            model_name='marketingpushmacro',
            index=models.Index(fields=['is_active', 'next_scheduled_at'], name='notificatio_macro_due_idx'),
        ),
    ]
