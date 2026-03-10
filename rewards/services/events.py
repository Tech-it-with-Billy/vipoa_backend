from rewards.domain.keys import profile_completion_key
from rewards.services.engine import PoaPointsEngine

PROFILE_COMPLETION_REWARD = 100

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
