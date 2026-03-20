from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.views.decorators.csrf import csrf_exempt


# -----------------------------------------
# SUPERUSER-ONLY SWAGGER PERMISSION
# -----------------------------------------
class IsSuperUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


# -----------------------------------------
# SWAGGER SCHEMA CONFIGURATION
# -----------------------------------------
schema_view = get_schema_view(
    openapi.Info(
        title="Vipoa API",
        default_version="v1",
        description="API documentation for the Vipoa backend.",
    ),
    public=False,
    permission_classes=[IsSuperUser],
)


# -----------------------------------------
# URL PATTERNS
# -----------------------------------------
urlpatterns = [
    path("admin/", admin.site.urls),

    # DRF login/logout (required for Swagger session auth)
    path("api-auth/", include("rest_framework.urls")),

    # ---- APP ROUTES ----
    path("api/jema/", include("jema.urls")),
    path("api/reviews/", include("reviews.urls")),
    path("api/products/", include("products.urls")),
    path("api/profiles/", include("profiles.urls")),
    path("api/poa-points/", include("rewards.urls")),  # alias
    path("api/rewards/", include("rewards.urls")),     # canonical
    path("api/surveys/", include(("surveys.urls", "surveys"), namespace="surveys")),
    path("api/diary/", include("diary.urls")),

    # ---- SWAGGER ROUTES (SUPERUSER ONLY) ----
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        csrf_exempt(schema_view.without_ui(cache_timeout=0)),
        name="schema-json",
    ),
    path(
        "swagger/",
        csrf_exempt(schema_view.with_ui("swagger", cache_timeout=0)),
        name="schema-swagger-ui",
    ),
    path(
        "redoc/",
        csrf_exempt(schema_view.with_ui("redoc", cache_timeout=0)),
        name="schema-redoc",
    ),
]


# -----------------------------------------
# MEDIA & STATIC (DEV MODE ONLY)
# -----------------------------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
