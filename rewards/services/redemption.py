from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from rewards.models import PoaPointsTransaction, Redemption
from rewards.services.wallet import get_or_create_wallet, wallet_snapshot


@dataclass(frozen=True)
class RedemptionResult:
    outcome: str  # "CONFIRMED" | "ALREADY_PROCESSED" | "INSUFFICIENT_FUNDS" | "FAILED"
    redemption: Redemption
    wallet: dict


REDEMPTION_TX_TYPE = "REDEMPTION_CONFIRMED"


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


@transaction.atomic
def create_and_confirm_redemption(
    *,
    user,
    reference_key: str,
    cost: int,
    provider: str = "",
    target: str = "",
    meta: Optional[dict] = None,
) -> RedemptionResult:
    """
    Spend PoaPoints in an idempotent, atomic way.

    Rules:
    - If same reference_key already CONFIRMED -> return existing result (idempotent)
    - If PENDING exists:
        - If wallet has funds -> confirm + create negative ledger tx
        - else -> mark FAILED, do not change wallet
    - Create ledger tx with reference_key (unique), amount = -cost
    """
    meta = meta or {}
    reference_key = reference_key.strip()

    # Lock wallet row (prevents race conditions on balance)
    wallet = get_or_create_wallet(user)

    # Lock or create redemption row
    redemption, created = Redemption.objects.select_for_update().get_or_create(
        user=user,
        reference_key=reference_key,
        defaults={
            "status": Redemption.Status.PENDING,
            "cost": cost,
            "provider": provider or "",
            "target": target or "",
            "meta": meta,
        },
    )

    # If it already exists, enforce consistent parameters (optional strictness)
    # This prevents a client from retrying same reference_key with different cost.
    if not created:
        if redemption.cost != cost:
            # Treat as failed attempt: idempotency key reused with different payload
            redemption.status = Redemption.Status.FAILED
            redemption.meta = {**(redemption.meta or {}), "error": "reference_key reused with different cost"}
            redemption.save(update_fields=["status", "meta"])
            return RedemptionResult("FAILED", redemption, wallet_snapshot(user, include_transactions=True))

        # If already confirmed, return idempotent success
        if redemption.status == Redemption.Status.CONFIRMED:
            return RedemptionResult("ALREADY_PROCESSED", redemption, wallet_snapshot(user, include_transactions=True))

        # If already failed, return idempotent failure
        if redemption.status == Redemption.Status.FAILED:
            return RedemptionResult("INSUFFICIENT_FUNDS", redemption, wallet_snapshot(user, include_transactions=True))

    # At this point, redemption is PENDING and payload is consistent
    # Check funds
    if wallet.balance < cost:
        redemption.status = Redemption.Status.FAILED
        redemption.meta = {**(redemption.meta or {}), "reason": "INSUFFICIENT_FUNDS", "balance": wallet.balance}
        redemption.save(update_fields=["status", "meta"])
        return RedemptionResult("INSUFFICIENT_FUNDS", redemption, wallet_snapshot(user, include_transactions=True))

    # Ledger idempotency safety:
    # If a tx already exists for this reference_key, do NOT double-spend.
    if PoaPointsTransaction.objects.filter(reference_key=reference_key).exists():
        # Ensure redemption is marked confirmed to reflect reality
        redemption.status = Redemption.Status.CONFIRMED
        if not redemption.confirmed_at:
            redemption.confirmed_at = timezone.now()
        redemption.save(update_fields=["status", "confirmed_at"])
        return RedemptionResult("ALREADY_PROCESSED", redemption, wallet_snapshot(user, include_transactions=True))

    # Apply spend: create negative tx then reduce balance
    PoaPointsTransaction.objects.create(
        user=user,
        account=wallet,
        amount=-cost,
        type=REDEMPTION_TX_TYPE,
        reference_key=reference_key,
        meta={
            "provider": provider,
            "target": target,
            **meta,
        },
    )

    wallet.balance -= cost
    wallet.save(update_fields=["balance", "updated_at"])

    redemption.status = Redemption.Status.CONFIRMED
    redemption.confirmed_at = timezone.now()
    redemption.provider = provider or redemption.provider or ""
    redemption.target = target or redemption.target or ""
    redemption.meta = {**(redemption.meta or {}), **meta}
    redemption.save(update_fields=["status", "confirmed_at", "provider", "target", "meta"])

    return RedemptionResult("CONFIRMED", redemption, wallet_snapshot(user, include_transactions=True))
