from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0005_supportconversation_supportconversationmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportconversation",
            name="last_operator_read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
