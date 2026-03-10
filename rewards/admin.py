from django.contrib import admin
from django.utils.html import format_html

from rewards.models import (
    PoaPointsAccount,
    PoaPointsTransaction,
    RewardClaim,
    Redemption,
)

# --------------------------------------------------
# PoaPoints Wallet Admin
# --------------------------------------------------
@admin.register(PoaPointsAccount)
class PoaPointsAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "balance",
        "status",
        "created_at",
        "updated_at",
    )
    search_fields = ("user__email", "user__username")
    list_filter = ("status",)
    readonly_fields = ("created_at", "updated_at")

    ordering = ("-updated_at",)


# --------------------------------------------------
# Ledger / Transactions Admin
# --------------------------------------------------
@admin.register(PoaPointsTransaction)
class PoaPointsTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "amount",
        "type",
        "reference_key",
        "created_at",
    )
    search_fields = (
        "reference_key",
        "user__email",
        "user__username",
    )
    list_filter = ("type", "created_at")
    readonly_fields = (
        "user",
        "account",
        "amount",
        "type",
        "reference_key",
        "created_at",
        "meta",
    )

    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# --------------------------------------------------
# Reward Claims (Shutdown Records)
# --------------------------------------------------
@admin.register(RewardClaim)
class RewardClaimAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "event_type",
        "reference_key",
        "status",
        "created_at",
        "applied_at",
    )
    search_fields = (
        "reference_key",
        "user__email",
        "user__username",
    )
    list_filter = ("event_type", "status")
    readonly_fields = (
        "user",
        "event_type",
        "reference_key",
        "event_id",
        "created_at",
        "applied_at",
        "meta",
    )

    ordering = ("-created_at",)


# --------------------------------------------------
# Redemptions (Spending)
# --------------------------------------------------
@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cost",
        "status",
        "provider",
        "target",
        "created_at",
        "confirmed_at",
    )
    search_fields = (
        "reference_key",
        "user__email",
        "user__username",
        "target",
    )
    list_filter = ("status", "provider")
    readonly_fields = (
        "user",
        "reference_key",
        "cost",
        "provider",
        "target",
        "created_at",
        "confirmed_at",
        "meta",
    )

    ordering = ("-created_at",)
