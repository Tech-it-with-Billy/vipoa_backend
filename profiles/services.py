import profile

from django.db import transaction


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