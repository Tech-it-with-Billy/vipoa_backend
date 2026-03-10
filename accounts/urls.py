from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    MeView,
    ChangePasswordView,
    GoogleLoginView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="accounts-register"),
    path("login/", LoginView.as_view(), name="accounts-login"),
    path("me/", MeView.as_view(), name="accounts-me"),
    path(
        "change-password/",
        ChangePasswordView.as_view(),
        name="accounts-change-password",
    ),

    # ✅ NEW GOOGLE LOGIN ROUTE
    path("google-login/", GoogleLoginView.as_view(), name="accounts-google-login"),
]
