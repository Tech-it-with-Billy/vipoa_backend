from datetime import date

def profile_completion_key(user_id: int) -> str:
    return f"PROFILE_COMPLETION:{user_id}"

def survey_completion_key(user_id: int, survey_id: int | None = None) -> str:
    return f"SURVEY_COMPLETION:{user_id}:{survey_id}" if survey_id else f"SURVEY_COMPLETION:{user_id}"

def review_approved_key(user_id: int, review_id: int) -> str:
    return f"REVIEW_APPROVED:{user_id}:{review_id}"

def share_confirmed_key(user_id: int, share_proof_id: int) -> str:
    return f"SHARE_CONFIRMED:{user_id}:{share_proof_id}"

def challenge_completed_key(user_id: int, challenge_id: int) -> str:
    return f"CHALLENGE_COMPLETED:{user_id}:{challenge_id}"

def streak_daily_key(user_id: int, day: date) -> str:
    return f"STREAK_DAILY:{user_id}:{day.isoformat()}"

def streak_weekly_key(user_id: int, year: int, week: int) -> str:
    return f"STREAK_WEEKLY:{user_id}:{year:04d}-W{week:02d}"

def referral_milestone_key(user_id: int, milestone: int) -> str:
    return f"REFERRAL_MILESTONE:{user_id}:{milestone}"

def first_jema_interaction_key(user_id: int) -> str:
    return f"FIRST_JEMA_INTERACTION:{user_id}"
