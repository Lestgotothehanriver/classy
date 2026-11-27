from django.contrib.auth.hashers import make_password
from django.db import migrations, models


def hash_existing_codes(apps, schema_editor):
    """Protect existing verification codes without invalidating active requests."""
    verification = apps.get_model("accounts", "PhoneVerification")
    for record in verification.objects.using(schema_editor.connection.alias).iterator():
        record.code = make_password(record.code)
        record.save(update_fields=["code"], using=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0033_instructor_public_id")]

    operations = [
        migrations.AlterField(
            model_name="phoneverification",
            name="code",
            field=models.CharField(max_length=128),
        ),
        migrations.RunPython(hash_existing_codes, migrations.RunPython.noop),
    ]
