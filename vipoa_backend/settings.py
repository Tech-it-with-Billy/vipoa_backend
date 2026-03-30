import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda *args, **kwargs: None

import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


# -----------------------------
# SECURITY
# -----------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    "api.vipoa.africa",
    ".railway.app",
    "ALLOWED_HOSTS",
    "vipoa.africa",
    "127.0.0.1",
    "localhost"
]

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = not DEBUG

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"


# -----------------------------
# THIRD PARTY KEYS
# -----------------------------

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")


# -----------------------------
# CSRF
# -----------------------------

CSRF_TRUSTED_ORIGINS = [
    "https://api.vipoa.africa",
    "https://vipoa.africa",
]


# -----------------------------
# APPLICATIONS
# -----------------------------

INSTALLED_APPS = [

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # Third Party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_yasg",

    # Local Apps
    "jema.apps.JemaConfig",
    "products",
    "reviews",
    "profiles.apps.ProfilesConfig",
    "surveys",
    "diary",
    "rewards",
]

SITE_ID = 1


# -----------------------------
# AUTHENTICATION
# -----------------------------

AUTH_USER_MODEL = "profiles.SupabaseUser"

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_JWKS_URL = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
SUPABASE_AUDIENCE = "authenticated"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "/admin/login/"


# -----------------------------
# DJANGO REST FRAMEWORK
# -----------------------------

REST_FRAMEWORK = {

    "DEFAULT_AUTHENTICATION_CLASSES": [
        "profiles.authentication.SupabaseAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# -----------------------------
# MIDDLEWARE
# -----------------------------

MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",

    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# -----------------------------
# CORS
# -----------------------------

CORS_ALLOWED_ORIGINS = [
    "http://localhost:51084", 
    "http://127.0.0.1:51084",
    "https://vipoa.africa",
    "https://www.vipoa.africa",
    "http://localhost:5173",
    "https://vipoa.netlify.app",
    "https://download.vipoa.africa",
    "https://vipoa.pages.dev",
]

CORS_ALLOW_CREDENTIALS = True


# -----------------------------
# URLS
# -----------------------------

ROOT_URLCONF = "vipoa_backend.urls"


# -----------------------------
# TEMPLATES
# -----------------------------

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


# -----------------------------
# WSGI
# -----------------------------

WSGI_APPLICATION = "vipoa_backend.wsgi.application"


# -----------------------------
# DATABASE
# -----------------------------

DATABASES = {

    "default": dj_database_url.config(

        default=os.environ.get(
            "DATABASE_URL",
            f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
        ),
        conn_max_age=600,
        ssl_require=True
    )
}


# -----------------------------
# STATIC FILES
# -----------------------------

STATIC_URL = "/static/"

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# -----------------------------
# MEDIA FILES
# -----------------------------

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# -----------------------------
# DEFAULT FIELD
# -----------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# -----------------------------
# SWAGGER
# -----------------------------

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


# -----------------------------
# DJANGO ALLAUTH
# -----------------------------

ACCOUNT_EMAIL_VERIFICATION = "none"

ACCOUNT_AUTHENTICATION_METHOD = "username_email"

ACCOUNT_EMAIL_REQUIRED = True

ACCOUNT_USERNAME_REQUIRED = True


# -----------------------------
# LOGGING
# -----------------------------

LOGGING = {

    "version": 1,

    "disable_existing_loggers": False,

    "handlers": {

        "console": {

            "class": "logging.StreamHandler",
        },
    },

    "root": {

        "handlers": ["console"],

        "level": "INFO",
    },
}


# -----------------------------
# REFERRAL REWARD CONFIG
# -----------------------------

REFERRAL_REWARD_MILESTONES = {
    1: 10,
    2: 10,
    3: 10,
    4: 10,
    5: 10,
    6: 10,
    7: 10,
    8: 10,
    9: 10,
}