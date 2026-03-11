import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vipoa_backend.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

USERNAME = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
EMAIL = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
PASSWORD = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "changeme123")

if not User.objects.filter(username=USERNAME).exists():
    print(f"Creating superuser {USERNAME}")
    User.objects.create_superuser(username=USERNAME, email=EMAIL, password=PASSWORD)
else:
    print(f"Superuser {USERNAME} already exists")