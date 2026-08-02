from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0021_review_resource_and_comment_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tutoringpost",
            name="field",
            field=models.CharField(
                blank=True,
                choices=[
                    ("문과", "문과"),
                    ("이과", "이과"),
                    ("예체능", "예체능"),
                    ("특성화", "특성화"),
                    ("기타", "기타"),
                ],
                max_length=20,
            ),
        ),
    ]
