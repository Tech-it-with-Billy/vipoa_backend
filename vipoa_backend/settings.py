import os
from pathlib import Path

# ``python-dotenv`` is an optional dependency used during development.  If it
# isn't installed (for example in a clean test environment) we simply skip
# loading the `.env` file rather than raising an ImportError.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency not required in tests
    load_dotenv = lambda *args, **kwargs: None

import dj_database_url

# read environment variables from a local .env file when present (development)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ``SECRET_KEY`` must be provided by the environment in production.  A
# fallback is only for development; do **not** commit a real secret key.
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

# ``DEBUG`` should be explicitly toggled via the environment. Railway will
# typically set DEBUG=False in production.
DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

# Allow hosts can be injected from Railway; we provide a reasonable default
# for local development.  Railway sets ``ALLOWED_HOSTS`` as a comma-separated
# list in its environment variables if you configure it that way.
ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    "api.vipoa.africa,vipoa.africa,127.0.0.1,localhost",
).split(",")

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

GOOGLE_CLIENT_ID = "your-google-client-id"

CSRF_TRUSTED_ORIGINS = [
    "https://api.vipoa.africa",
    "https://vipoa.africa",
]

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # 3rd Party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_yasg",        # <-- Required for Swagger



    # Your apps
    "accounts",
    "api",
    "jema",
    'products',
    'reviews',
    "profiles.apps.ProfilesConfig",
    'surveys',
    'diary',
    # 'poa_points',
    'rewards'
    
]

SITE_ID = 1

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
AUTHENTICATION_BACKENDS = [
    "accounts.admin_backend.SuperUserOnlyBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/admin/login/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",

    # CORS
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # REQUIRED FOR DJANGO-ALLAUTH
    

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = "vipoa_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "vipoa_backend.wsgi.application"

# ``dj_database_url.config`` will return an ``{}`` if no database URL is
# provided, so we supply a hard-coded sqlite entry for local development.
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
    )
}

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
# Use whitenoise's compressed manifest storage so that static assets are
# cached efficiently in production.  It requires running collectstatic during
# build.
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Remove STATICFILES_DIRS because static/ does NOT exist
# STATICFILES_DIRS = [ BASE_DIR / "static" ]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Swagger (superuser-only)
SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": True,
    "LOGIN_URL": "/admin/login/",
    "SECURITY_DEFINITIONS": {
        "TokenAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
        }
    },
}

# Django-Allauth
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = True

