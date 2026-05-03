from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Sequence, cast

from django.db import models

from ._simple_writes import MODEL_FIELD_METADATA_KEY

__all__ = [
    "ParentScopeSpec",
    "dataclass_parent_binding_field_name",
    "normalize_parent_scope",
    "parent_scope",
    "validate_parent_scope",
]


@dataclass(frozen=True)
class ParentScopeSpec:
    """Describe one nested parent-child route scope for a generated factory."""

    parent_model: type[models.Model]
    url_prefix: str
    parent_lookup_url_kwarg: str
    child_fk_field: str
    parent_lookup_field: str = "pk"
    bind_on_create: bool = True


def parent_scope(
    *,
    parent_model: type[models.Model],
    url_prefix: str,
    parent_lookup_url_kwarg: str,
    child_fk_field: str,
    parent_lookup_field: str = "pk",
    bind_on_create: bool = True,
) -> ParentScopeSpec:
    """Return one nested parent-child scope declaration.

    Example:

    ```python
    parent_scope(
        parent_model=Chargepoint,
        url_prefix="chargepoints/<int:chargepoint_pk>",
        parent_lookup_url_kwarg="chargepoint_pk",
        child_fk_field="chargepoint",
    )
    ```
    """
    return ParentScopeSpec(
        parent_model=parent_model,
        url_prefix=url_prefix,
        parent_lookup_url_kwarg=parent_lookup_url_kwarg,
        child_fk_field=child_fk_field,
        parent_lookup_field=parent_lookup_field,
        bind_on_create=bind_on_create,
    )


def normalize_parent_scope(
    parent_scope_spec: ParentScopeSpec | None,
) -> ParentScopeSpec | None:
    """Return the configured parent scope unchanged or None."""
    return parent_scope_spec


def validate_parent_scope(
    *,
    model: type[models.Model],
    parent_scope_spec: ParentScopeSpec | None,
    create_input: type[object] | None,
    update_input: type[object] | None,
    partial_update_input: type[object] | None,
    read_only: bool,
) -> None:
    """Validate nested parent-child scope configuration at factory construction."""
    if parent_scope_spec is None:
        return
    if not issubclass(parent_scope_spec.parent_model, models.Model):
        raise TypeError("parent_scope parent_model must be a Django model class.")
    if not parent_scope_spec.url_prefix.strip("/"):
        raise ValueError("parent_scope url_prefix must be a non-empty string.")
    if not parent_scope_spec.parent_lookup_url_kwarg:
        raise ValueError("parent_scope parent_lookup_url_kwarg must be a non-empty string.")
    if not parent_scope_spec.child_fk_field:
        raise ValueError("parent_scope child_fk_field must be a non-empty string.")
    child_field = model._meta.get_field(parent_scope_spec.child_fk_field)
    if not isinstance(child_field, models.ForeignKey):
        raise TypeError(
            f"parent_scope child_fk_field {parent_scope_spec.child_fk_field!r} "
            f"on {model.__name__} must be a ForeignKey."
        )
    if child_field.remote_field.model is not parent_scope_spec.parent_model:
        raise TypeError(
            f"parent_scope child_fk_field {parent_scope_spec.child_fk_field!r} on "
            f"{model.__name__} must point to {parent_scope_spec.parent_model.__name__}."
        )
    if read_only:
        return
    if parent_scope_spec.bind_on_create:
        validate_parent_binding_dataclass(
            dataclass_type=create_input,
            child_fk_field=parent_scope_spec.child_fk_field,
            action_name="create_input",
        )
        validate_parent_binding_dataclass(
            dataclass_type=update_input,
            child_fk_field=parent_scope_spec.child_fk_field,
            action_name="update_input",
        )
        validate_parent_binding_dataclass(
            dataclass_type=partial_update_input,
            child_fk_field=parent_scope_spec.child_fk_field,
            action_name="partial_update_input",
        )


def validate_parent_binding_dataclass(
    *,
    dataclass_type: type[object] | None,
    child_fk_field: str,
    action_name: str,
) -> None:
    """Ensure one request DTO can receive the parent value from the URL."""
    if dataclass_type is None:
        return
    binding_field = dataclass_parent_binding_field_name(
        dataclass_type=dataclass_type,
        child_fk_field=child_fk_field,
    )
    if binding_field is None:
        raise TypeError(
            f"{action_name} must declare a field mapped to {child_fk_field!r} or "
            f"{child_fk_field + '_id'!r} when parent_scope bind_on_create=True."
        )


def dataclass_parent_binding_field_name(
    *,
    dataclass_type: type[object],
    child_fk_field: str,
) -> str | None:
    """Return the DTO field name that maps to the child parent-FK slot."""
    model_targets = {child_fk_field, f"{child_fk_field}_id"}
    for dataclass_field in fields(cast(Any, dataclass_type)):
        mapped_name = cast(
            str,
            dataclass_field.metadata.get(MODEL_FIELD_METADATA_KEY, dataclass_field.name),
        )
        if mapped_name in model_targets:
            return dataclass_field.name
    return None
