from __future__ import annotations

from django.db import connection

__all__ = [
    "ensure_acl_tables_exist",
]


def ensure_acl_tables_exist() -> None:
    """Create missing ACL tables directly from models.

    This is intentionally opt-in. Projects that prefer normal Django migrations
    should keep it disabled and rely on `python -m django migrate`.
    """

    from .models import (
        AclAuditLog,
        AclGrant,
        AclGroup,
        AclGroupMember,
        AclPermission,
        AclResourceClosure,
        AclResourceNode,
    )

    existing_tables = set(connection.introspection.table_names())
    acl_models = (
        AclPermission,
        AclGroup,
        AclGroupMember,
        AclResourceNode,
        AclResourceClosure,
        AclGrant,
        AclAuditLog,
    )

    with connection.schema_editor() as schema_editor:
        for model in acl_models:
            if model._meta.db_table in existing_tables:
                continue
            schema_editor.create_model(model)
            existing_tables.add(model._meta.db_table)
