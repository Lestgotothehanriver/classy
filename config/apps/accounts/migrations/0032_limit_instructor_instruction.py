from django.db import migrations, models


def truncate_instructions(apps, schema_editor):
    instructor_model = apps.get_model("accounts", "Instructor")

    for instructor in instructor_model.objects.exclude(instruction=""):
        if len(instructor.instruction) > 300:
            instructor.instruction = instructor.instruction[:300]
            instructor.save(update_fields=["instruction"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0031_sync_subject_catalog"),
    ]

    operations = [
        migrations.RunPython(truncate_instructions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="instructor",
            name="instruction",
            field=models.TextField(blank=True, default="", max_length=300),
        ),
    ]
