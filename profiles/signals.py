from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Profile
from rewards.services.events import award_profile_completion


@receiver(post_save, sender=Profile)
def check_profile_completion(sender, instance: Profile, **kwargs):
    """
    Automatically award profile completion when all required fields are filled.

    This runs ONLY when profile is updated.
    Authentication layer guarantees profile exists.
    """

    if instance.profile_completed_awarded:
        return

    if instance.is_profile_complete():
        award_profile_completion(user=instance.user)

        instance.profile_completed_awarded = True
        instance.save(update_fields=["profile_completed_awarded"])