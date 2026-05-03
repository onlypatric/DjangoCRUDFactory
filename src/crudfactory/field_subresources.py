from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Sequence, cast

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from rest_framework import serializers

from .acl import ACLActionConfig, ACLMode

FieldPatchMode = Literal["replace", "merge"]

__all__ = ["FieldSubresourceSpec", "field_subresource"]


@dataclass(frozen=True)
class FieldSubresourceSpec:
    """Describe one generated detail endpoint over a single model field."""

    field_name: str
    methods: tuple[str, ...]
    patch_mode: FieldPatchMode
    url_path: str | None
    url_name: str | None
    read_acl: ACLActionConfig | None
    patch_acl: ACLActionConfig | None


def field_subresource(
    *,
    field_name: str,
    methods: tuple[str, ...] = ("get", "patch"),
    patch_mode: FieldPatchMode = "replace",
    url_path: str | None = None,
    url_name: str | None = None,
    read_acl: ACLActionConfig | None = None,
    patch_acl: ACLActionConfig | None = None,
    read_permission: str | None = None,
    update_permission: str | None = None,
    acl_mode: ACLMode = "scoped",
    unauthorized_as_404: bool = True,
) -> FieldSubresourceSpec:
    """Return a generated detail endpoint config for one model field.

    This feature is intended for CRUD-adjacent endpoints such as:

    - `GET /resource/{id}/metadata/`
    - `PATCH /resource/{id}/metadata/`
    """
    return FieldSubresourceSpec(
        field_name=field_name,
        methods=normalize_field_subresource_methods(methods),
        patch_mode=patch_mode,
        url_path=url_path,
        url_name=url_name,
        read_acl=resolve_field_subresource_acl(
            explicit_acl=read_acl,
            permission=read_permission,
            mode=acl_mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        patch_acl=resolve_field_subresource_acl(
            explicit_acl=patch_acl,
            permission=update_permission,
            mode=acl_mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
    )


def normalize_field_subresources(
    field_subresources: Sequence[FieldSubresourceSpec] | None,
) -> tuple[FieldSubresourceSpec, ...]:
    """Freeze optional field subresource specs for generated viewset stability."""
    if field_subresources is None:
        return ()
    return tuple(field_subresources)


def validate_field_subresources(
    *,
    model: type[models.Model],
    field_subresources: tuple[FieldSubresourceSpec, ...],
    read_only: bool,
) -> None:
    """Validate field subresource configuration at factory construction time."""
    seen_field_names: set[str] = set()
    for field_subresource_spec in field_subresources:
        validate_non_empty_field_name(field_subresource_spec.field_name)
        if field_subresource_spec.field_name in seen_field_names:
            msg = (
                f"Duplicate field subresource {field_subresource_spec.field_name!r}."
            )
            raise ValueError(msg)
        seen_field_names.add(field_subresource_spec.field_name)
        validate_field_subresource_model_field(
            model=model,
            field_name=field_subresource_spec.field_name,
            allow_patch="patch" in field_subresource_spec.methods,
        )
        validate_patch_mode(
            model=model,
            field_name=field_subresource_spec.field_name,
            patch_mode=field_subresource_spec.patch_mode,
        )
        if read_only and "patch" in field_subresource_spec.methods:
            msg = (
                f"Field subresource {field_subresource_spec.field_name!r} cannot "
                "enable PATCH on a read-only factory."
            )
            raise ValueError(msg)


def validate_field_subresource_model_field(
    *,
    model: type[models.Model],
    field_name: str,
    allow_patch: bool,
) -> None:
    """Ensure the configured model field exists and is suitable for the endpoint."""
    django_field = direct_model_field(model, field_name)
    if not getattr(django_field, "concrete", False):
        msg = f"Field subresource {model.__name__}.{field_name} must be concrete."
        raise TypeError(msg)
    if getattr(django_field, "many_to_many", False):
        msg = (
            f"Field subresource {model.__name__}.{field_name} cannot target many-to-many fields."
        )
        raise TypeError(msg)
    if allow_patch and not getattr(django_field, "editable", False):
        msg = f"Field subresource {model.__name__}.{field_name} is not editable."
        raise TypeError(msg)


def validate_patch_mode(
    *,
    model: type[models.Model],
    field_name: str,
    patch_mode: str,
) -> None:
    """Validate the requested patch semantics for one field endpoint."""
    if patch_mode not in {"replace", "merge"}:
        msg = "field_subresource patch_mode must be 'replace' or 'merge'."
        raise ValueError(msg)
    if patch_mode == "merge" and not isinstance(direct_model_field(model, field_name), models.JSONField):
        msg = (
            f"Field subresource {model.__name__}.{field_name} uses patch_mode='merge', "
            "but merge is only supported for JSONField in v1."
        )
        raise TypeError(msg)


def normalize_field_subresource_methods(methods: tuple[str, ...]) -> tuple[str, ...]:
    """Return lower-case methods after enforcing the V1 field subresource surface."""
    normalized_methods = tuple(method.lower() for method in methods)
    if not normalized_methods:
        msg = "Field subresources must expose at least one HTTP method."
        raise ValueError(msg)
    for method in normalized_methods:
        if method not in {"get", "patch"}:
            msg = "Field subresource methods must be 'get' and/or 'patch'."
            raise ValueError(msg)
    return normalized_methods


def resolve_field_subresource_acl(
    *,
    explicit_acl: ACLActionConfig | None,
    permission: str | None,
    mode: ACLMode,
    unauthorized_as_404: bool,
) -> ACLActionConfig | None:
    """Return one explicit ACL config or build a small permission-based one."""
    if explicit_acl is not None:
        return explicit_acl
    if permission is None:
        return None
    return ACLActionConfig(
        permission=permission,
        mode=mode,
        unauthorized_as_404=unauthorized_as_404,
    )


def direct_model_field(model: type[models.Model], field_name: str) -> models.Field:
    """Return one direct Django model field or raise a clear configuration error."""
    try:
        return cast(models.Field, model._meta.get_field(field_name))
    except FieldDoesNotExist as exc:
        msg = f"Field subresource {model.__name__}.{field_name} does not exist."
        raise ValueError(msg) from exc


def serializer_field_for_model_field(
    *,
    model: type[models.Model],
    field_name: str,
) -> serializers.Field:
    """Return the DRF serializer field used to validate one model field value."""
    meta_class = type("Meta", (), {"model": model, "fields": [field_name]})
    serializer_class = type(
        f"{model.__name__}{field_name.title()}FieldEndpointSerializer",
        (serializers.ModelSerializer,),
        {"Meta": meta_class},
    )
    serializer = cast(serializers.ModelSerializer[Any], serializer_class())
    serializer_field = serializer.fields[field_name]
    serializer_field.required = True
    serializer_field.allow_null = getattr(serializer_field, "allow_null", False)
    return deepcopy(serializer_field)


def read_field_payload(instance: models.Model, field_name: str) -> object:
    """Return one model field value suitable for a direct API response."""
    return getattr(instance, field_name)


def validated_field_payload(
    *,
    model: type[models.Model],
    field_name: str,
    payload: object,
) -> object:
    """Validate one raw request payload against the model field serializer."""
    serializer_field = serializer_field_for_model_field(model=model, field_name=field_name)
    return serializer_field.run_validation(payload)


def apply_field_subresource_patch(
    *,
    instance: models.Model,
    field_name: str,
    patch_mode: FieldPatchMode,
    payload: object,
) -> object:
    """Apply a replace or merge patch and persist the field update."""
    if patch_mode == "replace":
        setattr(instance, field_name, payload)
        instance.save(update_fields=[field_name])
        return getattr(instance, field_name)

    current_value = getattr(instance, field_name)
    if current_value is None:
        current_value = {}
    if not isinstance(current_value, dict) or not isinstance(payload, dict):
        raise serializers.ValidationError(
            {
                field_name: [
                    "Merge patch requires both the stored value and payload to be dictionaries."
                ]
            }
        )
    merged_value = dict(current_value)
    merged_value.update(payload)
    setattr(instance, field_name, merged_value)
    instance.save(update_fields=[field_name])
    return getattr(instance, field_name)


def field_subresource_payload_label(
    *,
    model: type[models.Model],
    field_name: str,
) -> str:
    """Return a small human-readable type label for docs."""
    django_field = direct_model_field(model, field_name)
    if isinstance(django_field, models.JSONField):
        return "JSON object"
    if isinstance(django_field, (models.CharField, models.TextField)):
        return "string"
    if isinstance(django_field, models.BooleanField):
        return "boolean"
    if isinstance(django_field, models.IntegerField):
        return "integer"
    if isinstance(django_field, models.DecimalField):
        return "decimal"
    if isinstance(django_field, models.FloatField):
        return "float"
    return django_field.get_internal_type()


def validate_non_empty_field_name(field_name: str) -> None:
    """Reject empty model field names in field subresource declarations."""
    if not field_name:
        msg = "field_subresource field_name must be a non-empty string."
        raise ValueError(msg)
