from __future__ import annotations

import sys

from django.apps import AppConfig

from .config import get_crudfactory_settings


class CrudFactoryConfig(AppConfig):
    """Optional Django app config for CRUDFactory's ORM-backed ACL models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "crudfactory"
    verbose_name = "CRUDFactory"

    def ready(self) -> None:
        settings = get_crudfactory_settings()
        if not settings.acl_enabled:
            return
        if not settings.acl_auto_create_tables:
            return
        if is_management_command_that_manages_schema():
            return
        from .acl_tables import ensure_acl_tables_exist

        ensure_acl_tables_exist()


def is_management_command_that_manages_schema() -> bool:
    """Skip eager table creation during schema-management commands."""
    schema_commands = {
        "makemigrations",
        "migrate",
        "showmigrations",
        "sqlmigrate",
    }
    return any(command in sys.argv for command in schema_commands)
