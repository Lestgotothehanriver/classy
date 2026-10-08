from django.db import migrations, models


def move_emergency_notices_to_list(apps, schema_editor):
    """삭제되는 긴급 모달 공지를 목록 공지로 안전하게 보존합니다."""
    Notice = apps.get_model("notice", "Notice")
    Notice.objects.filter(exposure_type="EMERGENCY_MODAL").update(
        exposure_type="LIST",
        exposure_ends_at=None,
        banner_order=None,
    )


class Migration(migrations.Migration):
    dependencies = [("notice", "0001_initial")]

    operations = [
        migrations.RunPython(move_emergency_notices_to_list, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notice",
            name="exposure_type",
            field=models.CharField(
                choices=[("LIST", "목록만"), ("HOME_BANNER", "홈 배너 · 앱 공지 모달")],
                db_index=True,
                default="LIST",
                max_length=20,
            ),
        ),
    ]
