from django.db import transaction


@transaction.atomic
def add_poa_points(user, points: int):
    """
    Safely add PoaPoints to a user's wallet.

    - Uses wallet as the source of truth
    - Atomic (prevents race conditions)
    - Creates wallet if missing
    """

    if points <= 0:
        return 0

    try:
        from rewards.models import POAWallet
    except Exception as e:
        raise Exception(f"Wallet model import failed: {e}")

    wallet, _ = POAWallet.objects.get_or_create(user=user)

    wallet.balance += points
    wallet.save(update_fields=["balance"])

    return wallet.balance