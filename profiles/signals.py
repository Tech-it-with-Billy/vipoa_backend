from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile
from rewards.services.events import award_profile_completion

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


@receiver(post_save, sender=Profile)
def check_profile_completion(sender, instance: Profile, **kwargs):
    """
    Automatically award profile completion when all required fields are filled.
    """
    if instance.is_profile_complete() and not instance.profile_completed_awarded:
        award_profile_completion(user=instance.user)
        instance.profile_completed_awarded = True
        instance.save(update_fields=["profile_completed_awarded"])