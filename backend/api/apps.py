from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'api'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Import signals to register them
        import api.signals  # noqa: F401
