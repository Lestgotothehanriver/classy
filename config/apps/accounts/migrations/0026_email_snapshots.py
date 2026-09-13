from django.db import migrations, models


def populate_emails(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, relation, field in (
        ('UserConsent', 'user', 'user_email'),
        ('UserSanction', 'target_user', 'target_user_email'),
    ):
        model = apps.get_model('accounts', model_name)
        for row in model.objects.using(alias).select_related(relation).iterator():
            user = getattr(row, relation)
            if user is not None:
                model.objects.using(alias).filter(pk=row.pk).update(**{field: user.email})


class Migration(migrations.Migration):
    dependencies = [('accounts', '0025_user_google_play_account_token')]
    operations = [
        migrations.AddField(
            model_name='userconsent', name='user_email',
            field=models.EmailField(default='', max_length=254), preserve_default=False,
        ),
        migrations.AddField(
            model_name='usersanction', name='target_user_email',
            field=models.EmailField(default='', max_length=254, help_text='제재 대상 사용자의 이메일 스냅샷'),
            preserve_default=False,
        ),
        migrations.RunPython(populate_emails, migrations.RunPython.noop),
    ]
