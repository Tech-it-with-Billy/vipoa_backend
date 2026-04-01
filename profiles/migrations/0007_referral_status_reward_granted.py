from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0006_add_referred_by_to_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='referral',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('pending', 'Pending'),
                    ('verified', 'Verified'),
                    ('rejected', 'Rejected'),
                ],
                default='verified',
            ),
        ),
        migrations.AddField(
            model_name='referral',
            name='reward_granted',
            field=models.BooleanField(default=False),
        ),
    ]
