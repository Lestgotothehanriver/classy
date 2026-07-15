from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0019_remove_virtual_accounts_add_resource_registration"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="tutoringresource",
            name="payback_account_holder",
        ),
        migrations.RemoveField(
            model_name="tutoringresource",
            name="payback_account_number",
        ),
        migrations.RemoveField(
            model_name="tutoringresource",
            name="payback_bank",
        ),
    ]
