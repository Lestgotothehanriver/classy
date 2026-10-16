from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0028_deletedaccountfile_user_deleted_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromotionCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("signup_starts_at", models.DateTimeField()),
                ("signup_ends_at", models.DateTimeField()),
                ("is_active", models.BooleanField(default=True)),
                ("benefit_months", models.PositiveSmallIntegerField(default=3)),
                ("tutoring_registration_limit", models.PositiveSmallIntegerField(default=3)),
                ("tutoring_commission_rate_bps", models.PositiveIntegerField(default=50)),
                ("lecture_settlement_fee_rate_bps", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-signup_starts_at", "-id"]},
        ),
        migrations.CreateModel(
            name="InstructorPromotionBenefit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("benefit_starts_at", models.DateTimeField()),
                ("benefit_ends_at", models.DateTimeField()),
                ("tutoring_registration_limit", models.PositiveSmallIntegerField(default=3)),
                ("tutoring_commission_rate_bps", models.PositiveIntegerField(default=50)),
                ("lecture_settlement_fee_rate_bps", models.PositiveIntegerField(default=0)),
                ("used_tutoring_registration_count", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="benefits", to="promotions.promotioncampaign")),
                ("instructor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="promotion_benefits", to="accounts.instructor")),
            ],
        ),
        migrations.AddConstraint(
            model_name="instructorpromotionbenefit",
            constraint=models.UniqueConstraint(fields=("campaign", "instructor"), name="unique_campaign_instructor_benefit"),
        ),
        migrations.AddIndex(
            model_name="instructorpromotionbenefit",
            index=models.Index(fields=["instructor", "benefit_ends_at"], name="promotion_instructor_end_idx"),
        ),
    ]
