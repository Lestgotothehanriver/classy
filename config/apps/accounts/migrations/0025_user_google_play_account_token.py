import uuid

from django.db import migrations, models


def populate_google_play_account_tokens(apps, schema_editor):
    """Assign a unique Google Play account token to every existing user."""

    User = apps.get_model('accounts', 'User')
    for user in User.objects.filter(google_play_account_token__isnull=True).iterator():
        user.google_play_account_token = uuid.uuid4()
        user.save(update_fields=['google_play_account_token'])


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0024_user_apple_app_account_token_user_cash_debt'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='google_play_account_token',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(
            populate_google_play_account_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='user',
            name='google_play_account_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
