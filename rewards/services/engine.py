from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from rewards.domain.constants import RewardClaimStatus
from rewards.models import RewardClaim, PoaPointsTransaction
from rewards.services.wallet import get_or_create_wallet


@dataclass(frozen=True)
class EngineResult:
    outcome: str  # "APPLIED" | "ALREADY_REWARDED" | "NOT_ELIGIBLE" | "REJECTED"
    reference_key: str
    wallet_balance: int


class PoaPointsEngine:
    """
    Central Processor (spec §3.1)
    - Validates event eligibility
    - Enforces idempotency/shutdown via RewardClaim(reference_key)
    - Creates ledger transaction
    - Updates wallet balance
    - Marks claim APPLIED
    """

    @staticmethod
    def process_award(
        *,
        user,
        event_type: str,
        reference_key: str,
        amount: int,
        event_id: Optional[str] = None,
        meta: Optional[dict] = None,
        require_verified: bool = False,
        is_verified: bool = True,
        is_done: bool = True,
    ) -> EngineResult:
        """
        Generic award processor used by all event types.

        Inputs:
        - user: request.user
        - event_type: e.g PROFILE_COMPLETION
        - reference_key: unique shutdown key (spec §5)
        - amount: integer points to award
        - event_id/meta: for traceability
        - require_verified/is_verified/is_done: keep simple now;
          later you can compute these based on your domain rules.
        """
        meta = meta or {}

        if amount <= 0:
            # No-op safety; earning must be positive
            return EngineResult("REJECTED", reference_key, wallet_balance=PoaPointsEngine._current_balance(user))

        # Eligibility checks
        if not is_done:
            return EngineResult("NOT_ELIGIBLE", reference_key, wallet_balance=PoaPointsEngine._current_balance(user))
        if require_verified and not is_verified:
            return EngineResult("NOT_ELIGIBLE", reference_key, wallet_balance=PoaPointsEngine._current_balance(user))

        with transaction.atomic():
            wallet = get_or_create_wallet(user)

            # Lock or create claim row for this reward opportunity
            claim, created = RewardClaim.objects.select_for_update().get_or_create(
                user=user,
                reference_key=reference_key,
                defaults={
                    "event_type": event_type,
                    "event_id": event_id,
                    "status": RewardClaimStatus.VERIFIED if (not require_verified or is_verified) else RewardClaimStatus.PENDING,
                    "meta": meta,
                },
            )

            # If already applied, stop (global shutdown rule)
            if claim.status == RewardClaimStatus.APPLIED:
                return EngineResult("ALREADY_REWARDED", reference_key, wallet_balance=wallet.balance)

            # Update claim status if needed
            if require_verified and not is_verified:
                claim.status = RewardClaimStatus.PENDING
                claim.meta = {**claim.meta, **meta}
                claim.save(update_fields=["status", "meta"])
                return EngineResult("NOT_ELIGIBLE", reference_key, wallet_balance=wallet.balance)

            claim.status = RewardClaimStatus.VERIFIED
            claim.meta = {**claim.meta, **meta}
            claim.save(update_fields=["status", "meta"])

            # Ledger idempotency guard (extra safety)
            # If reference_key already has a tx, treat as already rewarded
            if PoaPointsTransaction.objects.filter(reference_key=reference_key).exists():
                # Ensure claim is APPLIED if tx exists (optional reconcile)
                claim.status = RewardClaimStatus.APPLIED
                if not claim.applied_at:
                    claim.applied_at = timezone.now()
                claim.save(update_fields=["status", "applied_at"])
                return EngineResult("ALREADY_REWARDED", reference_key, wallet_balance=wallet.balance)

            # Apply: create transaction then update wallet
            PoaPointsTransaction.objects.create(
                user=user,
                account=wallet,
                amount=amount,
                type=event_type,
                reference_key=reference_key,
                meta=meta,
            )

            wallet.balance += amount
            wallet.save(update_fields=["balance", "updated_at"])

            claim.status = RewardClaimStatus.APPLIED
            claim.applied_at = timezone.now()
            claim.save(update_fields=["status", "applied_at"])

            return EngineResult("APPLIED", reference_key, wallet_balance=wallet.balance)

    @staticmethod
    def _current_balance(user) -> int:
        from rewards.models import PoaPointsAccount
        wallet = PoaPointsAccount.objects.filter(user=user).only("balance").first()
        return wallet.balance if wallet else 0
