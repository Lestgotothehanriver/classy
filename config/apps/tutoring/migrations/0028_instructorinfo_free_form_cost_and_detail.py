from django.db import migrations, models


def convert_legacy_costs(apps, schema_editor):
    instructor_info_model = apps.get_model("tutoring", "InstructorInfo")

    for profile in instructor_info_model.objects.all().only("pk", "cost"):
        value = profile.cost
        if value in (None, 0):
            profile.cost_text = "협의 후 결정"
        elif value % 10000 == 0:
            profile.cost_text = f"월 {value // 10000}만원 이하"
        else:
            profile.cost_text = f"월 {value:,}원 이하"
        profile.save(update_fields=["cost_text"])


class Migration(migrations.Migration):

    dependencies = [
        ("tutoring", "0027_registration_submission_finalization"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorinfo",
            name="cost_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunPython(convert_legacy_costs, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="instructorinfo",
            name="cost",
        ),
        migrations.RenameField(
            model_name="instructorinfo",
            old_name="cost_text",
            new_name="cost",
        ),
        migrations.AlterField(
            model_name="instructorinfo",
            name="etc",
            field=models.TextField(blank=True),
        ),
    ]
