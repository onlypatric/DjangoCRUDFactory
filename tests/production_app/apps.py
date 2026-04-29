from __future__ import annotations

from django.apps import AppConfig


class ProductionAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tests.production_app"
    label = "production_app"
