from django.contrib import admin
from .models import Profile, SupabaseUser


@admin.register(SupabaseUser)
class SupabaseUserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "full_name",
        "is_active",
        "is_staff",
        "is_superuser",
    )
    list_filter = ("is_active", "is_staff", "is_superuser")
    ordering = ("email",)
    search_fields = ("email", "full_name")
    readonly_fields = ("date_joined", "updated_at")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "name",
        "gender",
        "age",
        "current_weight_kg",
        "current_height_cm",
        "bmi",
        "bmi_category",
        "goal",
        "diet",
        "activity_level",
        "day_streak",
        "poa_points",
        "profile_completed_awarded",
        "updated_at",
    )
    readonly_fields = (
        "poa_points",
        "day_streak",
        "profile_completed_awarded",
        "age",
        "bmi",
        "bmi_category",
        "updated_at",
    )