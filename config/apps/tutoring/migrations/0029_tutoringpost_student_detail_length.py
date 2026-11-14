from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0028_instructorinfo_free_form_cost_and_detail"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tutoringpost",
            name="situation",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AlterField(
            model_name="tutoringpost",
            name="etc",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
