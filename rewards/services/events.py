from rewards.domain.keys import profile_completion_key, referral_milestone_key
from rewards.services.engine import PoaPointsEngine
from rewards.domain.constants import RewardEventType, RewardClaimStatus
from datetime import date

PROFILE_COMPLETION_REWARD = 100

REFERRAL_MILESTONE_REWARD = 300

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
