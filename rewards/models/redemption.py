from django.conf import settings
from django.db import models


class Redemption(models.Model):
    """
    Spending PoaPoints.
    Must create a negative transaction on CONFIRMED.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FAILED = "FAILED", "Failed"
        REVERSED = "REVERSED", "Reversed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="redemptions",
    )

    reference_key = models.CharField(max_length=255)  # idempotency for spend
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)

    cost = models.PositiveIntegerField()  # points to spend
    provider = models.CharField(max_length=80, blank=True, default="")  # e.g "MPESA", "VOUCHER"
    target = models.CharField(max_length=120, blank=True, default="")   # e.g phone number / voucher id

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "redemption"
        constraints = [
            models.UniqueConstraint(fields=["user", "reference_key"], name="uq_redemption_user_key"),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Redemption(user_id={self.user_id}, cost={self.cost}, status={self.status})"
