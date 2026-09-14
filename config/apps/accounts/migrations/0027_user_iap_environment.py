from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0026_email_snapshots')]
    operations = [
        migrations.AlterField(
            model_name='userconsent', name='doc_type',
            field=models.CharField(max_length=20, choices=[
                ('terms', '이용약관'), ('privacy', '개인정보처리방침'),
                ('marketing', '마케팅 수신'), ('cash_terms', '캐시 이용약관'),
            ]),
        ),
        migrations.AddField(
            model_name='user', name='iap_environment',
            field=models.CharField(
                max_length=10, default='PRODUCTION', editable=False,
                choices=[('PRODUCTION', 'Production'), ('SANDBOX', 'Sandbox')],
            ),
        ),
    ]
