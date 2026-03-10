from django.contrib import admin
from .models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    # Display all relevant fields
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

    list_filter = ("gender", "diet", "goal", "region")
    search_fields = ("user__username", "name", "location", "works_at")
    ordering = ("-updated_at",)

    # Make certain fields read-only (derived and gamification)
    readonly_fields = (
        "poa_points",
        "day_streak",
        "profile_completed_awarded",
        "age",
        "bmi",
        "bmi_category",
        "updated_at",
    )

    # Optional: group fields in sections for clarity
    fieldsets = (
        ("Basic Info", {
            "fields": ("user", "name", "email", "gender", "dob", "location")
        }),
        ("Health Metrics", {
            "fields": (
                "current_weight_kg",
                "current_height_cm",
                "target_weight_kg",
                "target_height_cm",
                "bmi",
                "bmi_category",
                "age",
                "goal",
                "activity_level",
                "diet",
                "eating_realities",
                "medical_restrictions",
                "allergies",
                "dislikes",
                "cooking_skills",
            )
        }),
        ("Lifestyle & Work", {
            "fields": (
                "religion",
                "occupational_status",
                "works_at",
                "income_level",
                "region",
            )
        }),
        ("Gamification", {
            "fields": ("poa_points", "day_streak", "profile_completed_awarded")
        }),
        ("Timestamps", {
            "fields": ("updated_at",)
        }),
    )