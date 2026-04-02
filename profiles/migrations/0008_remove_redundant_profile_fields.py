from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0007_referral_status_reward_granted"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="profile",
            name="location",
        ),
        migrations.RemoveField(
            model_name="profile",
            name="target_height_cm",
        ),
        migrations.RemoveField(
            model_name="profile",
            name="occupational_status",
        ),
        migrations.RemoveField(
            model_name="profile",
            name="works_at",
        ),
        migrations.RemoveField(
            model_name="profile",
            name="income_level",
        ),
    ]
