# profiles/services.py
from django.db import transaction
from .models import Profile


@transaction.atomic
def add_poa_points(profile: Profile, points: int, reason: str = ""):
    """
    Safely add PoaPoints to a user's profile.

    - Atomic (prevents race conditions)
    - Centralized
    """

    if points <= 0:
        return profile.poa_points

    profile.poa_points += points
    profile.save(update_fields=["poa_points"])

    return profile.poa_points
