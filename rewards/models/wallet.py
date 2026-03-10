from django.conf import settings
from django.db import models


class PoaPointsAccount(models.Model):
    """
    One wallet per user. This is the single source of truth for current balance.
    """
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        LOCKED = "LOCKED", "Locked"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="poa_wallet",
    )

    balance = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "poa_points_account"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"PoaWallet(user_id={self.user_id}, balance={self.balance})"
