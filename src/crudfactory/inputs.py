from __future__ import annotations

from dataclasses import fields
from typing import Any, TypeVar, cast, get_type_hints

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
        return dataclass_type(**data)
    except TypeError as exc:
        msg = f"Could not construct {dataclass_type.__name__}: {exc}"
        raise serializers.ValidationError(msg) from exc
