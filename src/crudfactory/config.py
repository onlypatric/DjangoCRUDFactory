from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

__all__ = [
    "CrudFactorySettings",
    "get_crudfactory_settings",
]


@dataclass(frozen=True)
class CrudFactorySettings:
    """Small typed view over Django settings used by CRUDFactory."""

    acl_enabled: bool = True
    acl_auto_create_tables: bool = False


def get_crudfactory_settings() -> CrudFactorySettings:
    """Return CRUDFactory settings from Django settings.

    Supported configuration styles:

    ```python
    CRUDFACTORY = {
        "ACL_ENABLED": True,
        "ACL_AUTO_CREATE_TABLES": False,
    }
    ```

    and legacy top-level flags:

    ```python
    CRUDFACTORY_ACL_ENABLED = True
    CRUDFACTORY_ACL_AUTO_CREATE_TABLES = False
    ```
    """

    configured = getattr(settings, "CRUDFACTORY", {})
    if not isinstance(configured, dict):
        configured = {}

    acl_enabled = bool(
        configured.get(
            "ACL_ENABLED",
            getattr(settings, "CRUDFACTORY_ACL_ENABLED", True),
        )
    )
    acl_auto_create_tables = bool(
        configured.get(
            "ACL_AUTO_CREATE_TABLES",
            getattr(settings, "CRUDFACTORY_ACL_AUTO_CREATE_TABLES", False),
        )
    )

    return CrudFactorySettings(
        acl_enabled=acl_enabled,
        acl_auto_create_tables=acl_auto_create_tables,
    )
