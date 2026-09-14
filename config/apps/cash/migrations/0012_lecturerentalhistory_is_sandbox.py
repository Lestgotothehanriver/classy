from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0027_user_iap_environment'),
        ('cash', '0011_cashlot_cashlotusage_and_refund_state'),
    ]
    operations = [
        migrations.AddField(
            model_name='lecturerentalhistory', name='is_sandbox',
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
