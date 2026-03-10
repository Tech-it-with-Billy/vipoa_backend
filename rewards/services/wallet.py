from django.db import transaction
from rewards.models import PoaPointsAccount, PoaPointsTransaction


@transaction.atomic
def get_or_create_wallet(user):
    """
    Ensure the user always has exactly one PoaPoints wallet.
    Locked for concurrency safety.
    """
    wallet, _ = PoaPointsAccount.objects.select_for_update().get_or_create(
        user=user,
        defaults={
            "balance": 0,
            "status": PoaPointsAccount.Status.ACTIVE,
        },
    )
    return wallet


def wallet_snapshot(user, include_transactions=False, tx_limit=10):
    """
    Standard wallet output contract (Spec §10).
    """
    wallet, _ = PoaPointsAccount.objects.get_or_create(
        user=user,
        defaults={"balance": 0, "status": PoaPointsAccount.Status.ACTIVE},
    )

    data = {
        "balance": wallet.balance,
        "status": wallet.status,
        "current_title": None,     # will be wired later
        "unlocked_perks": [],      # will be wired later
    }

    if include_transactions:
        txs = PoaPointsTransaction.objects.filter(
            user=user
        ).order_by("-created_at")[:tx_limit]

        data["recent_transactions"] = [
            {
                "amount": t.amount,
                "type": t.type,
                "reference_key": t.reference_key,
                "created_at": t.created_at,
                "meta": t.meta,
            }
            for t in txs
        ]

    return data
