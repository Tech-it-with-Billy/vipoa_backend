# api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("profile/<int:user_id>/", views.get_user_profile, name="user-profile"),
    path("profile/update/", views.update_user_profile, name="update-user-profile"),
]
