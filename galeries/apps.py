from django.apps import AppConfig


class GaleriesConfig(AppConfig):
    name = "galeries"

    def ready(self):
        from . import signals  # noqa: F401
