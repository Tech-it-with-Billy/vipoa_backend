from django.conf import settings
from django.db import models


class PoaPointsTransaction(models.Model):
    """
    Immutable transaction ledger.
    +amount for earning, -amount for spending.
    reference_key is the idempotency key linking to RewardClaim or Redemption.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="poa_transactions",
    )

    account = models.ForeignKey(
        "rewards.PoaPointsAccount",
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    amount = models.IntegerField()  # can be negative
    type = models.CharField(max_length=80)  # e.g PROFILE_COMPLETION, REDEMPTION_CONFIRMED
    reference_key = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "poa_points_transaction"
        constraints = [
            # ✅ Ledger idempotency: same reference_key must not generate multiple tx
            models.UniqueConstraint(fields=["reference_key"], name="uq_poa_tx_reference_key"),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self) -> str:
        return f"Tx(user_id={self.user_id}, amount={self.amount}, type={self.type})"
