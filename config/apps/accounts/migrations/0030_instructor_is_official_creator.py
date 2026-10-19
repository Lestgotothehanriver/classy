from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0029_alter_subject_number")]

    operations = [
        migrations.AddField(
            model_name="instructor",
            name="is_official_creator",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddConstraint(
            model_name="instructor",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_official_creator", True)),
                fields=("is_official_creator",),
                name="accounts_single_official_creator",
            ),
        ),
    ]
