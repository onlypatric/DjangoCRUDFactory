from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from django.db import models
from django.utils import timezone

LifecycleMode = Literal["timestamp-delete", "boolean-archive", "boolean-active"]

__all__ = [
    "LifecycleConfig",
    "archive_lifecycle",
    "soft_delete_lifecycle",
]


@dataclass(frozen=True)
class LifecycleConfig:
    """Soft-delete/archive lifecycle rules for one CRUDFactory resource."""

    mode: LifecycleMode
    field_name: str
    restore_action: bool = True
    restore_action_name: str = "restore"
    restore_url_path: str = "restore"
    restore_url_name: str | None = None
    include_archived_param: str | None = "include_archived"
    hide_archived_detail: bool = True


def soft_delete_lifecycle(
    *,
    deleted_field: str,
    restore_action: bool = True,
    include_archived_param: str | None = "include_archived",
    hide_archived_detail: bool = True,
) -> LifecycleConfig:
    """Return timestamp-based soft-delete behavior using a nullable datetime field."""
    return LifecycleConfig(
        mode="timestamp-delete",
        field_name=deleted_field,
        restore_action=restore_action,
        include_archived_param=include_archived_param,
        hide_archived_detail=hide_archived_detail,
    )


def archive_lifecycle(
    *,
    archived_field: str | None = None,
    active_field: str | None = None,
    restore_action: bool = True,
    include_archived_param: str | None = "include_archived",
    hide_archived_detail: bool = True,
) -> LifecycleConfig:
    """Return boolean archive behavior using either an archived or active flag."""
    if (archived_field is None) == (active_field is None):
        msg = "archive_lifecycle requires exactly one of archived_field or active_field."
        raise TypeError(msg)
    if archived_field is not None:
        return LifecycleConfig(
            mode="boolean-archive",
            field_name=archived_field,
            restore_action=restore_action,
            include_archived_param=include_archived_param,
            hide_archived_detail=hide_archived_detail,
        )
    return LifecycleConfig(
        mode="boolean-active",
        field_name=active_field or "",
        restore_action=restore_action,
        include_archived_param=include_archived_param,
        hide_archived_detail=hide_archived_detail,
    )


def lifecycle_filter_queryset(
    queryset: models.QuerySet[models.Model],
    lifecycle: LifecycleConfig,
) -> models.QuerySet[models.Model]:
    """Return the queryset restricted to active rows."""
    if lifecycle.mode == "timestamp-delete":
        return queryset.filter(**{f"{lifecycle.field_name}__isnull": True})
    if lifecycle.mode == "boolean-archive":
        return queryset.filter(**{lifecycle.field_name: False})
    return queryset.filter(**{lifecycle.field_name: True})


def apply_delete_lifecycle(instance: models.Model, lifecycle: LifecycleConfig) -> None:
    """Mark one instance as archived instead of hard-deleting it."""
    if lifecycle.mode == "timestamp-delete":
        setattr(instance, lifecycle.field_name, timezone.now())
    elif lifecycle.mode == "boolean-archive":
        setattr(instance, lifecycle.field_name, True)
    else:
        setattr(instance, lifecycle.field_name, False)
    instance.save(update_fields=[lifecycle.field_name])


def apply_restore_lifecycle(instance: models.Model, lifecycle: LifecycleConfig) -> None:
    """Restore one archived instance to its active state."""
    if lifecycle.mode == "timestamp-delete":
        setattr(instance, lifecycle.field_name, None)
    elif lifecycle.mode == "boolean-archive":
        setattr(instance, lifecycle.field_name, False)
    else:
        setattr(instance, lifecycle.field_name, True)
    instance.save(update_fields=[lifecycle.field_name])


def instance_is_archived(instance: models.Model, lifecycle: LifecycleConfig) -> bool:
    """Return whether the instance is currently archived."""
    value = getattr(instance, lifecycle.field_name)
    if lifecycle.mode == "timestamp-delete":
        return isinstance(value, datetime)
    if lifecycle.mode == "boolean-archive":
        return bool(value)
    return not bool(value)


def lifecycle_include_archived_requested(
    lifecycle: LifecycleConfig,
    raw_value: object,
) -> bool:
    """Return True when a list request explicitly asks to include archived rows."""
    if lifecycle.include_archived_param is None or not isinstance(raw_value, str):
        return False
    normalized = raw_value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}
