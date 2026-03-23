from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile
from rewards.models.wallet import PoaPointsAccount

User = get_user_model()


@receiver(post_save, sender=User)
def ensure_profile_wallet(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={"name": instance.full_name, "email": instance.email},
        )
        PoaPointsAccount.objects.get_or_create(user=instance, defaults={"balance": 0})


@receiver(post_save, sender=User)
def sync_profile_identity(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        profile = instance.profile
        changed = False
        if profile.name != instance.full_name:
            profile.name = instance.full_name
            changed = True
        if profile.email != instance.email:
            profile.email = instance.email
            changed = True
        if changed:
            profile.save(update_fields=["name", "email"])