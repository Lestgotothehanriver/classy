from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tutoring', '0013_studentreview_created_at_alter_tutoringpost_grade'),
    ]

    operations = [
        migrations.AddField(
            model_name='tutoringresource',
            name='fee_payment_status',
            field=models.CharField(
                choices=[
                    ('PENDING', '입금 대기'),
                    ('AWAITING_CONFIRMATION', '확인 대기'),
                    ('PAID', '납부 완료'),
                    ('FAILED', '납부 실패'),
                ],
                default='PENDING',
                max_length=30,
            ),
        ),
    ]
