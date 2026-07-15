import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0018_tutoringproposal_created_at"),
    ]

    operations = [
        migrations.DeleteModel(name="TossWebhookEvent"),
        migrations.DeleteModel(name="VirtualAccountPayment"),
        migrations.AddField(
            model_name="tutoringresource",
            name="registration",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="resource",
                to="tutoring.tutoringregistration",
            ),
        ),
    ]
