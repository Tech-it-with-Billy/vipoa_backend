from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile
from rewards.models import POAWallet
from rewards.services.events import award_profile_completion

User = get_user_model()


@receiver(post_save, sender=User)
def ensure_profile_wallet(sender, instance, created, **kwargs):
    # Ensure Profile
    Profile.objects.get_or_create(
        user=instance,
        defaults={"name": instance.full_name, "email": instance.email},
    )

    # Ensure Wallet
    POAWallet.objects.get_or_create(user=instance, defaults={"balance": 0})


@receiver(post_save, sender=User)
def sync_profile_identity(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        profile = instance.profile
        profile.name = instance.full_name
        profile.email = instance.email
        profile.save(update_fields=["name", "email"])