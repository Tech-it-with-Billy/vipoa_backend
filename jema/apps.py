from django.apps import AppConfig


class JemaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jema"

    def ready(self):
        import jema.signals
