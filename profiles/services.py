import profile

from django.db import transaction

from typing import Dict, Any
from .models import Profile


@transaction.atomic
def add_poa_points(profile: profile.Profile, points: int, reason: str = ""):
    """
    Safely add PoaPoints to a user's wallet.

    - Uses wallet as the source of truth
    - Atomic (prevents race conditions)
    - Creates wallet if missing
    """

    if points <= 0:
        return profile.poa_points

    wallet = profile.user.poa_wallet
    wallet.balance += points
    wallet.save(update_fields=["balance"])

    return wallet.balance


def get_user_profile_context(user) -> Dict[str, Any]:
    """
    Returns FULL structured profile data for personalization (Jema, AI, recommendations).

    - Includes all model fields
    - Includes computed properties
    - Safe for missing/null values
    """

    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return {}

    return {
        # -----------------------------
        # BASIC INFO
        # -----------------------------
        "name": profile.name or "",
        "gender": profile.gender or "",
        "age": profile.age,
        "region": profile.region or "",

        # -----------------------------
        # HEALTH METRICS
        # -----------------------------
        "current_weight_kg": profile.current_weight_kg,
        "current_height_cm": profile.current_height_cm,
        "target_weight_kg": profile.target_weight_kg,
        "target_height_cm": profile.target_height_cm,
        "bmi": profile.bmi,
        "bmi_category": profile.bmi_category,
        "bmr": profile.bmr,
        "tdee": profile.tdee,

        # -----------------------------
        # GOALS & ACTIVITY
        # -----------------------------
        "goal": profile.goal or "",
        "activity_level": profile.activity_level or "",

        # -----------------------------
        # DIET & RESTRICTIONS
        # -----------------------------
        "diet": profile.diet or "",
        "eating_realities": profile.eating_realities or "",
        "medical_restrictions": profile.medical_restrictions or "",
        "allergies": profile.allergies or "",
        "dislikes": profile.dislikes or "",
        "cooking_skills": profile.cooking_skills or "",

        # -----------------------------
        # LIFESTYLE
        # -----------------------------
        "religion": profile.religion or "",
        "income_level": profile.income_level or "",

    }