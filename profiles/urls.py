from django.urls import path
from .views import ProfileCompletionStatusView, ProfileMeView, ProfileUpdateView

app_name = "profiles"

urlpatterns = [
    # Get and Patch current user's profile
    path("me/", ProfileMeView.as_view(), name="profile-me"),

    # Update current user's profile
    path("update/", ProfileUpdateView.as_view(), name="profile-update"),

    # Check profile completion status
    path("status/", ProfileCompletionStatusView.as_view(), name="profile-status"),
]
