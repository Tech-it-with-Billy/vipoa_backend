from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):

    if created:
        Profile.objects.create(
            user=instance,
            name=getattr(instance, "full_name", ""),
            email=getattr(instance, "email", ""),
        )


@receiver(post_save, sender=User)
def sync_profile_identity(sender, instance, **kwargs):

    if hasattr(instance, "profile"):
        profile = instance.profile
        profile.name = getattr(instance, "full_name", "")
        profile.email = getattr(instance, "email", "")
        profile.save(update_fields=["name", "email"])