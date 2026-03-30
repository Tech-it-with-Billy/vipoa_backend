from rewards.domain.keys import profile_completion_key, referral_milestone_key, jema_first_interaction_key
from rewards.services.engine import PoaPointsEngine
from rewards.domain.constants import RewardEventType
from datetime import date

from profiles.models import SupabaseUser
from django.contrib.auth import get_user_model
from rewards.services.events import award_referral_milestone

PROFILE_COMPLETION_REWARD = 100

REFERRAL_MILESTONE_REWARD = 90

FIRST_JEMA_INTERACTION_REWARD = 30

def award_profile_completion(*, user):
    return PoaPointsEngine.process_award(
        user=user,
        event_type="PROFILE_COMPLETION",
        reference_key=profile_completion_key(user.id),
        amount=PROFILE_COMPLETION_REWARD,
        meta={"source": "profiles"},
        require_verified=False,
        is_done=True,
    )


User = get_user_model()

def trigger_referral_milestone(supabase_sub: str, milestone: int, count: int):
    """
    Trigger referral milestone reward, mapping Supabase sub -> Django user
    """
    try:
        supabase_user = SupabaseUser.objects.get(supabase_sub=supabase_sub)
        user = supabase_user.user
    except SupabaseUser.DoesNotExist:
        logger.warning(f"No Django user found for Supabase sub {supabase_sub}")
        return None

    result = award_referral_milestone(user=user, milestone=milestone, count=count)
    logger.info(f"Referral milestone reward for user {user.id}: {result.outcome}")
    return result

def award_jema_first_interaction(*, user):
    return PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.JEMA_FIRST_INTERACTION,
        reference_key=jema_first_interaction_key(user.id),
        amount=JEMA_FIRST_INTERACTION_REWARD,
        meta={"source": "jema"},
        require_verified=False,
        is_done=True,
    )
