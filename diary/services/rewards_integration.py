from rewards.services.engine import PoaPointsEngine
from rewards.domain.keys import streak_daily_key
from datetime import date

def award_diary_points_to_wallet(user, diary_entry):
    """
    Award points from a diary entry to the rewards wallet.
    Each diary entry points are added as a daily streak reward.
    """
    if diary_entry.points_earned <= 0:
        return None  # No points to award

    reference_key = streak_daily_key(user.id, diary_entry.date)
    result = PoaPointsEngine.process_award(
        user=user,
        event_type="STREAK_DAILY",
        reference_key=reference_key,
        amount=diary_entry.points_earned,
        event_id=str(diary_entry.id),
        meta={
            "source": "diary",
            "meals_logged": sum(bool(getattr(diary_entry, meal)) for meal in ["breakfast", "lunch", "dinner", "snack"]),
            "water_glasses": diary_entry.water_glasses,
        },
        require_verified=False,
        is_verified=True,
        is_done=True,
    )
    return result