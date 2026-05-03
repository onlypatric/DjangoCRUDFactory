from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, TypeVar, cast, get_args, get_origin, get_type_hints

from rest_framework import serializers

from .dataclass_serializers import unwrap_optional_type

__all__: list[str] = []

D = TypeVar("D")


def serializer_to_dataclass(
    serializer: serializers.Serializer,
    dataclass_type: type[D],
    *,
    fill_missing_optional: bool = False,
) -> D:
    """Construct a request dataclass from a validated DRF serializer.

    The serializer has already performed API validation.  This function is the
    small bridge between DRF's dictionary-shaped `validated_data` and the
    dataclass object that the user's create/update hook receives.
    """
    data = serializer_validated_dict(serializer)

    if fill_missing_optional:
        fill_missing_optional_fields(data, dataclass_type)

    return construct_dataclass(dataclass_type, data)


def serializer_validated_dict(serializer: serializers.Serializer) -> dict[str, object]:
    """Return a mutable dictionary copy of serializer.validated_data."""
    return cast(dict[str, object], dict(serializer.validated_data))


def fill_missing_optional_fields(data: dict[str, object], dataclass_type: type[D]) -> None:
    """Add `None` for omitted optional fields on PATCH DTOs.

    PATCH requests often omit fields.  Dataclass constructors still need values
    for fields without defaults, so CRUDFactory normalizes omitted optionals to
    None before calling the user's partial-update hook.
    """
    type_hints = get_type_hints(dataclass_type)

    for dataclass_field in fields(cast(Any, dataclass_type)):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        _, is_optional = unwrap_optional_type(field_type)
        if is_optional and dataclass_field.name not in data:
            data[dataclass_field.name] = None


def construct_dataclass(dataclass_type: type[D], data: dict[str, object]) -> D:
    """Instantiate a dataclass and convert constructor errors to DRF errors."""
    try:
        return dataclass_type(
            **dataclass_constructor_values(dataclass_type, data)
        )
    except TypeError as exc:
        msg = f"Could not construct {dataclass_type.__name__}: {exc}"
        raise serializers.ValidationError(msg) from exc


def project_dataclass(
    source_value: object,
    dataclass_type: type[D],
    *,
    fill_missing_optional: bool = False,
) -> D:
    """Construct one dataclass from overlapping attributes on another object."""
    projected_data = projected_dataclass_values(source_value, dataclass_type)
    if fill_missing_optional:
        fill_missing_optional_fields(projected_data, dataclass_type)
    return construct_dataclass(dataclass_type, projected_data)


def override_dataclass(
    source_value: D,
    overrides: dict[str, object],
    *,
    fill_missing_optional: bool = False,
) -> D:
    """Return a dataclass copy with one or more field values replaced.

    CRUDFactory occasionally needs to trust URL-derived values over request-body
    values, for example when a nested child resource must always stay bound to
    the parent object identified in the route.  This helper rebuilds a
    dataclass using the current field values plus explicit overrides.
    """
    dataclass_type = type(source_value)
    projected_data = projected_dataclass_values(source_value, dataclass_type)
    projected_data.update(overrides)
    if fill_missing_optional:
        fill_missing_optional_fields(projected_data, dataclass_type)
    return construct_dataclass(dataclass_type, projected_data)


def dataclass_constructor_values(
    dataclass_type: type[D],
    data: dict[str, object],
) -> dict[str, object]:
    """Convert nested validated payloads into dataclass constructor values."""
    type_hints = get_type_hints(dataclass_type)
    constructor_values: dict[str, object] = {}

    for dataclass_field in fields(cast(Any, dataclass_type)):
        if dataclass_field.name not in data:
            continue
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        constructor_values[dataclass_field.name] = construct_field_value(
            field_type=field_type,
            value=data[dataclass_field.name],
        )

    return constructor_values


def projected_dataclass_values(
    source_value: object,
    dataclass_type: type[D],
) -> dict[str, object]:
    """Return constructor values shared between an object and a target dataclass."""
    constructor_values: dict[str, object] = {}
    for dataclass_field in fields(cast(Any, dataclass_type)):
        if not hasattr(source_value, dataclass_field.name):
            continue
        constructor_values[dataclass_field.name] = getattr(
            source_value,
            dataclass_field.name,
        )
    return constructor_values


def construct_field_value(*, field_type: object, value: object) -> object:
    """Return one dataclass field value, recursing into nested DTO shapes."""
    inner_type, allow_null = unwrap_optional_type(field_type)
    if value is None:
        if allow_null:
            return None
        return value

    if isinstance(inner_type, type) and is_dataclass(inner_type):
        if not isinstance(value, dict):
            return value
        return construct_dataclass(inner_type, cast(dict[str, object], value))

    origin = get_origin(inner_type)
    if origin is list:
        child_type = list_child_type(inner_type)
        if not isinstance(value, list):
            return value
        return [
            construct_field_value(field_type=child_type, value=child_value)
            for child_value in value
        ]

    return value


def list_child_type(field_type: object) -> object:
    """Return the child item type for one `list[T]` annotation."""
    args = get_args(field_type)
    if not args:
        return object
    return args[0]
