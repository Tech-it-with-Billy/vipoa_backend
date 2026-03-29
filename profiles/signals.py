from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile, Referral
from rewards.models.wallet import PoaPointsAccount
from rewards.services.events import award_profile_completion, award_referral_milestone

User = get_user_model()


@receiver(post_save, sender=User)
def ensure_profile_wallet(sender, instance, created, **kwargs):
    """
    Ensure Profile and Wallet exist for each user.
    """
    Profile.objects.get_or_create(
        user=instance,
        defaults={"name": instance.full_name, "email": instance.email},
    )
    PoaPointsAccount.objects.get_or_create(user=instance, defaults={"balance": 0})


@receiver(post_save, sender=User)
def sync_profile_identity(sender, instance, **kwargs):
    """
    Keep Profile name/email in sync with SupabaseUser
    """
    if hasattr(instance, "profile"):
        profile = instance.profile
        profile.name = instance.full_name
        profile.email = instance.email
        profile.save(update_fields=["name", "email"])


@receiver(post_save, sender=Profile)
def check_profile_completion(sender, instance: Profile, created, **kwargs):
    """
    Award profile completion points once.
    """
    if created or instance.profile_completed_awarded:
        return

    if instance.is_profile_complete():
        award_profile_completion(user=instance.user)
        Profile.objects.filter(pk=instance.pk).update(profile_completed_awarded=True)


@receiver(post_save, sender=Referral)
def check_referral_milestone(sender, instance: Referral, created, **kwargs):
    """
    Award points once when a user reaches 30 successful referrals.
    """
    if not created:
        return

    referrer_profile = instance.referrer
    total_referrals = Referral.objects.filter(referrer=referrer_profile).count()

    # Only award once when reaching exactly 30 referrals
    if total_referrals == 30:
        award_referral_milestone(referrer_profile.user)