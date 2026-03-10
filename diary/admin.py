from django.contrib import admin
from .models import DiaryEntry

@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "points_earned",
        "breakfast",
        "lunch",
        "dinner",
        "snack",
        "water_glasses",
        "streak_display",
        "created_at_display",
        "updated_at_display",
    )
    list_filter = ("date", "user")
    search_fields = ("user__username", "breakfast", "lunch", "dinner", "snack")
    ordering = ("-date",)
    readonly_fields = ("points_earned", "streak_display", "created_at_display", "updated_at_display")

    # Callables for admin display
    def streak_display(self, obj):
        return getattr(obj, "streak", 0)
    streak_display.short_description = "Streak"

    def created_at_display(self, obj):
        return getattr(obj, "created_at", None)
    created_at_display.short_description = "Created At"

    def updated_at_display(self, obj):
        return getattr(obj, "updated_at", None)
    updated_at_display.short_description = "Updated At"