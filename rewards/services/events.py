from rewards.domain.keys import (
    profile_completion_key,
    referral_milestone_key,
    jema_first_interaction_key,
    share_confirmed_key,
    challenge_completed_key,
)
from rewards.services.engine import PoaPointsEngine
from rewards.domain.constants import RewardEventType
from rewards.models import PoaPointsTransaction
from datetime import date

PROFILE_COMPLETION_REWARD = 100

REFERRAL_MILESTONE_REWARD = 300

FIRST_JEMA_INTERACTION_REWARD = 30

# Share rewards
SHARE_REWARD_PER_SHARE = 10
SHARE_MILESTONE_THRESHOLD = 9  # Award when user reaches 9 shares
SHARE_MILESTONE_BONUS = 80  # Additional bonus to reach 90 total (10 * 9)

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

def award_referral_milestone(*, user, milestone: int, count: int, amount: int | None = None):
    ref_key = referral_milestone_key(user.id, milestone)
    reward_amount = REFERRAL_MILESTONE_REWARD if amount is None else amount

    return PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.REFERRAL_MILESTONE,
        reference_key=ref_key,
        amount=reward_amount,
        meta={"milestone": milestone, "count": count},
        require_verified=False,
        is_verified=True,
        is_done=True,
    )

def award_jema_first_interaction(*, user):
    return PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.JEMA_FIRST_INTERACTION,
        reference_key=jema_first_interaction_key(user.id),
        amount=FIRST_JEMA_INTERACTION_REWARD,
        meta={"source": "jema"},
        require_verified=False,
        is_done=True,
    )


def award_share_confirmed(*, user, share_proof_id: int):
    """
    Award points when a user confirms sharing with another user.
    - 10 points per share
    - Additional 80 points (90 total) when user reaches 9 shares
    """
    ref_key = share_confirmed_key(user.id, share_proof_id)
    
    # Award base points for this share
    result = PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.SHARE_CONFIRMED,
        reference_key=ref_key,
        amount=SHARE_REWARD_PER_SHARE,
        meta={"share_proof_id": share_proof_id},
        require_verified=False,
        is_done=True,
    )
    
    # Check if this is the milestone share (9th share)
    if result.outcome == "APPLIED":
        share_count = PoaPointsTransaction.objects.filter(
            user=user,
            type=RewardEventType.SHARE_CONFIRMED,
        ).count()
        
        if share_count == SHARE_MILESTONE_THRESHOLD:
            # Award milestone bonus
            milestone_key = f"SHARE_MILESTONE:{user.id}:9"
            PoaPointsEngine.process_award(
                user=user,
                event_type=RewardEventType.SHARE_CONFIRMED,
                reference_key=milestone_key,
                amount=SHARE_MILESTONE_BONUS,
                meta={"milestone": 9, "bonus": True},
                require_verified=False,
                is_done=True,
            )
    
    return result


def award_challenge_completed(*, user, challenge_id: int, points: int):
    """
    Award points when a user completes a challenge.
    """
    ref_key = challenge_completed_key(user.id, challenge_id)
    
    return PoaPointsEngine.process_award(
        user=user,
        event_type=RewardEventType.CHALLENGE_COMPLETED,
        reference_key=ref_key,
        amount=points,
        meta={"challenge_id": challenge_id},
        require_verified=False,
        is_done=True,
    )

