from django.db import migrations, transaction
import secrets

def generate_referral_codes(apps, schema_editor):
    Profile = apps.get_model("profiles", "Profile")
    
    with transaction.atomic():
        for profile in Profile.objects.all():
            if not profile.referral_code:
                # Generate a unique code safely
                while True:
                    code = secrets.token_hex(6).upper()
                    if not Profile.objects.filter(referral_code=code).exists():
                        profile.referral_code = code
                        profile.save(update_fields=["referral_code"])
                        break

class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0002_profile_referral_code_referral"),
    ]

    operations = [
        migrations.RunPython(generate_referral_codes),
    ]