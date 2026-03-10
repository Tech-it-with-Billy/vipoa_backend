from django.conf import settings
from django.db import models
from rewards.domain.constants import RewardClaimStatus


class RewardClaim(models.Model):
    """
    Reward shutdown + lifecycle tracking.
    Once a reference_key is APPLIED for a user, it must never be applied again.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reward_claims",
    )

    reference_key = models.CharField(max_length=255)
    event_type = models.CharField(max_length=80)

    # event_id is optional because some events are "per user" (e.g. profile completion)
    event_id = models.CharField(max_length=120, null=True, blank=True)

    status = models.CharField(
        max_length=12,
        choices=RewardClaimStatus.CHOICES,
        default=RewardClaimStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    # extra context: store references like survey_id, review_id etc.
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "reward_claim"
        constraints = [
            # ✅ Global shutdown rule: a reward opportunity key must be unique per user
            models.UniqueConstraint(fields=["user", "reference_key"], name="uq_reward_claim_user_key"),
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["reference_key"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self) -> str:
        return f"RewardClaim(user_id={self.user_id}, key={self.reference_key}, status={self.status})"
