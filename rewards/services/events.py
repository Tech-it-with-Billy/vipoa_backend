from rewards.domain.keys import profile_completion_key, referral_milestone_key, first_jema_interaction_key
from rewards.services.engine import PoaPointsEngine
from rewards.domain.constants import RewardEventType
from datetime import date

PROFILE_COMPLETION_REWARD = 100

REFERRAL_MILESTONE_REWARD = 300

FIRST_JEMA_INTERACTION_REWARD = 50

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

def award_referral_milestone(*, user, milestone: int, count: int):
    ref_key = referral_milestone_key(user.id, milestone)

    return PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.REFERRAL_MILESTONE,
        reference_key=ref_key,
        amount=REFERRAL_MILESTONE_REWARD,
        meta={"milestone": milestone, "count": count},
        require_verified=False,
        is_verified=True,
        is_done=True,
    )

def award_first_jema_interaction(*, user):
    """
    Award points for first Jema chat interaction.
    Only awarded once per user.
    """
    return PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.FIRST_JEMA_INTERACTION,
        reference_key=first_jema_interaction_key(user.id),
        amount=FIRST_JEMA_INTERACTION_REWARD,
        meta={"source": "jema"},
        require_verified=False,
        is_done=True,
    )
