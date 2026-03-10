from django.contrib import admin
from .models import SurveyDefinition, SurveyQuestion, SurveyResponse


class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1
    fields = ("order", "key", "label", "field_type", "is_required", "options")
    ordering = ("order",)


@admin.register(SurveyDefinition)
class SurveyDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "points_reward", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    inlines = [SurveyQuestionInline]


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ("survey", "user", "submitted_at")
    list_filter = ("survey", "submitted_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("answers", "metadata")
