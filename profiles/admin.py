from django.contrib import admin
from .models import Profile

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
    readonly_fields = ("poa_points", "day_streak", "profile_completed_awarded", "age", "bmi", "bmi_category", "updated_at")