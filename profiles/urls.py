from django.urls import path
from .views import (
    ProfileMeView,
    ProfileUpdateView,
    ProfileCompletionStatusView,
    ReferralCreateView,
    ReferralCountView,
    ReferralLeaderboardView,
)

urlpatterns = [
    # -----------------------------
    # PROFILE ENDPOINTS
    # -----------------------------
    path("me/", ProfileMeView.as_view(), name="profile-me"),
    path("update/", ProfileUpdateView.as_view(), name="profile-update"),
    path("completion-status/", ProfileCompletionStatusView.as_view(), name="profile-completion-status"),

    # -----------------------------
    # REFERRAL ENDPOINTS
    # -----------------------------
    path("referral/create/", ReferralCreateView.as_view(), name="referral-create"),
    path("referral/count", ReferralCountView.as_view()),
    path("referral/count/", ReferralCountView.as_view(), name="referral-count"),
    path("referral/leaderboard/", ReferralLeaderboardView.as_view(), name="referral-leaderboard"),
]