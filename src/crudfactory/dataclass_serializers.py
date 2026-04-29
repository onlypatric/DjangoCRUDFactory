from __future__ import annotations

import datetime as dt
from dataclasses import MISSING, Field, fields, is_dataclass
from decimal import Decimal
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from rest_framework import serializers

from .validators import (
    Validator,
    field_has_choices_validator,
    field_has_length_validator,
    field_has_range_validator,
    field_has_regex_validator,
    validators_from_field,
)

_NoneType = type(None)
_SERIALIZER_CACHE: dict[tuple[type[Any], str], type[serializers.Serializer]] = {}

__all__: list[str] = []


def build_serializer_from_dataclass(
    dataclass_type: type[Any],
    *,
    name: str,
) -> type[serializers.Serializer]:
    """Create a DRF Serializer class that mirrors a request dataclass.

    The generated class is intentionally simple: one serializer field per
    dataclass field.  Persistence does not happen here; the serializer only
    validates incoming API data before CRUDFactory constructs the user's input
    dataclass and passes it to the configured write hook.
    """
    ensure_dataclass_type("dataclass_type", dataclass_type)
    cache_key = (dataclass_type, name)
    cached_serializer = _SERIALIZER_CACHE.get(cache_key)
    if cached_serializer is not None:
        return cached_serializer

    serializer_fields = build_serializer_fields(dataclass_type)
    serializer_class = type(name, (serializers.Serializer,), serializer_fields)
    _SERIALIZER_CACHE[cache_key] = serializer_class
    return serializer_class


def build_serializer_fields(dataclass_type: type[Any]) -> dict[str, serializers.Field]:
    """Return DRF fields for every field on a dataclass."""
    serializer_fields: dict[str, serializers.Field] = {}
    type_hints = get_type_hints(dataclass_type)

    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        serializer_fields[dataclass_field.name] = build_serializer_field(
            field_type,
            dataclass_field.name,
            required=is_required_dataclass_field(dataclass_field),
            dataclass_field=dataclass_field,
        )

    return serializer_fields


def build_serializer_field(
    field_type: Any,
    field_name: str,
    *,
    required: bool = True,
    dataclass_field: Field[Any] | None = None,
) -> serializers.Field:
    """Build one DRF serializer field from one supported Python type.

    v1 deliberately supports a small, obvious set of request DTO field types.
    Unsupported types fail during factory construction so a bad API contract is
    discovered at import/test time instead of on the first production request.
    """
    inner_type, allow_null = unwrap_optional_type(field_type)
    origin = get_origin(inner_type)
    kwargs = serializer_field_kwargs(
        required=required and not allow_null,
        allow_null=allow_null,
    )

    if inner_type is str:
        validators = validators_for_field(dataclass_field)
        return serializers.CharField(validators=validators, **kwargs)
    if inner_type is int:
        validators = validators_for_field(dataclass_field)
        return serializers.IntegerField(validators=validators, **kwargs)
    if inner_type is float:
        validators = validators_for_field(dataclass_field)
        return serializers.FloatField(validators=validators, **kwargs)
    if inner_type is bool:
        validators = validators_for_field(dataclass_field)
        return serializers.BooleanField(validators=validators, **kwargs)
    if inner_type is dt.date:
        validators = validators_for_field(dataclass_field)
        return serializers.DateField(validators=validators, **kwargs)
    if inner_type is dt.datetime:
        validators = validators_for_field(dataclass_field)
        return serializers.DateTimeField(validators=validators, **kwargs)
    if inner_type is Decimal:
        validators = validators_for_field(dataclass_field)
        return serializers.DecimalField(
            max_digits=38,
            decimal_places=18,
            validators=validators,
            **kwargs,
        )
    if inner_type is UUID:
        validators = validators_for_field(dataclass_field)
        return serializers.UUIDField(validators=validators, **kwargs)
    if origin is list:
        validators = validators_for_field(dataclass_field)
        return build_list_serializer_field(inner_type, field_name, kwargs, validators)

    raise_unsupported_field_type(field_name, inner_type)
    raise AssertionError("raise_unsupported_field_type should always raise.")


def build_list_serializer_field(
    list_type: Any,
    field_name: str,
    kwargs: dict[str, Any],
    validators: list[Validator],
) -> serializers.ListField:
    """Build a ListField for `list[T]` where T is a supported primitive type."""
    child_type = first_type_argument_or_any(list_type)
    child_field = build_list_child_field(child_type, field_name)
    return serializers.ListField(child=child_field, validators=validators, **kwargs)


def build_list_child_field(field_type: Any, field_name: str) -> serializers.Field:
    """Build the child field for a list while rejecting nested/optional values."""
    inner_type, allow_null = unwrap_optional_type(field_type)
    if allow_null:
        msg = f"List field {field_name!r} cannot use optional child values in v1."
        raise TypeError(msg)
    if get_origin(inner_type) is not None:
        msg = f"Nested list field {field_name!r} is not supported in v1."
        raise TypeError(msg)
    return build_serializer_field(inner_type, field_name, required=True)


def validators_for_field(
    dataclass_field: Field[Any] | None,
) -> list[Validator]:
    """Return validators declared in dataclass metadata for one field."""
    if dataclass_field is None:
        return []
    return validators_from_field(dataclass_field)


def serializer_field_kwargs(*, required: bool, allow_null: bool) -> dict[str, Any]:
    """Return common keyword arguments shared by generated DRF fields."""
    return {"required": required, "allow_null": allow_null}


def unwrap_optional_type(field_type: Any) -> tuple[Any, bool]:
    """Return `(inner_type, True)` for `Optional[T]` and `T | None`.

    Non-optional unions are not part of the v1 contract.  They are returned
    unchanged and later rejected by `build_serializer_field`.
    """
    origin = get_origin(field_type)
    if origin not in (Union, UnionType):
        return field_type, False

    args = get_args(field_type)
    if len(args) == 2 and _NoneType in args:
        inner_type = args[0] if args[1] is _NoneType else args[1]
        return inner_type, True
    return field_type, False


def first_type_argument_or_any(field_type: Any) -> Any:
    """Return the first generic argument, or Any for an unparameterized list."""
    args = get_args(field_type)
    if not args:
        return Any
    return args[0]


def ensure_dataclass_type(name: str, value: type[Any]) -> None:
    """Raise if a factory input type is not a dataclass class."""
    if not isinstance(value, type) or not is_dataclass(value):
        msg = f"{name} must be a dataclass type."
        raise TypeError(msg)


def validate_supported_dataclass_fields(dataclass_type: type[Any]) -> None:
    """Validate that every dataclass field can become a DRF serializer field."""
    type_hints = get_type_hints(dataclass_type)
    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        validate_metadata_matches_field_type(dataclass_field, field_type)
        build_serializer_field(
            field_type,
            dataclass_field.name,
            dataclass_field=dataclass_field,
        )


def validate_metadata_matches_field_type(
    dataclass_field: Field[Any],
    field_type: Any,
) -> None:
    """Ensure validator metadata is attached only to compatible field types."""
    inner_type, _ = unwrap_optional_type(field_type)
    if field_has_regex_validator(dataclass_field) and not type_supports_regex(inner_type):
        msg = (
            f"Field {dataclass_field.name!r} uses regex validation, "
            "but regex can only be used on str fields."
        )
        raise TypeError(msg)
    if field_has_range_validator(dataclass_field) and not type_supports_range(inner_type):
        msg = (
            f"Field {dataclass_field.name!r} uses range validation, "
            "but range_ can only be used on int, float, Decimal, date, "
            "or datetime fields."
        )
        raise TypeError(msg)
    if field_has_length_validator(dataclass_field) and not type_supports_length(inner_type):
        msg = (
            f"Field {dataclass_field.name!r} uses length validation, "
            "but length can only be used on str or list fields."
        )
        raise TypeError(msg)
    if field_has_choices_validator(dataclass_field) and get_origin(inner_type) is list:
        msg = (
            f"Field {dataclass_field.name!r} uses choices validation, "
            "but choices cannot be used on list fields in v1."
        )
        raise TypeError(msg)


def type_supports_regex(field_type: Any) -> bool:
    """Return True when regex validation can apply to this field type."""
    return field_type is str


def type_supports_range(field_type: Any) -> bool:
    """Return True when min/max value validation can apply to this field type."""
    return field_type in (int, float, Decimal, dt.date, dt.datetime)


def type_supports_length(field_type: Any) -> bool:
    """Return True when min/max length validation can apply to this field type."""
    return field_type is str or get_origin(field_type) is list


def validate_partial_update_dataclass(dataclass_type: type[Any]) -> None:
    """Ensure PATCH DTOs can be safely constructed from partial request data.

    CRUDFactory fills omitted optional PATCH fields with None.  A required
    non-optional field would make that impossible, so we fail at configuration
    time with a clear message.
    """
    type_hints = get_type_hints(dataclass_type)
    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        _, is_optional = unwrap_optional_type(field_type)
        if is_optional or has_dataclass_default(dataclass_field):
            continue
        msg = (
            "partial_update_input fields must be optional or define defaults. "
            f"Field {dataclass_field.name!r} on {dataclass_type.__name__} is required."
        )
        raise ValueError(msg)


def is_required_dataclass_field(dataclass_field: Field[Any]) -> bool:
    """Return True when a dataclass field has no default/default_factory."""
    return not has_dataclass_default(dataclass_field)


def has_dataclass_default(dataclass_field: Field[Any]) -> bool:
    """Return True when a dataclass field can be omitted from construction."""
    return (
        dataclass_field.default is not MISSING
        or dataclass_field.default_factory is not MISSING
    )


def raise_unsupported_field_type(field_name: str, field_type: Any) -> None:
    """Raise a consistent error for unsupported request DTO field types."""
    msg = (
        f"Unsupported field type for {field_name!r}: {field_type!r}. "
        "Supported types are str, int, float, bool, date, datetime, Decimal, UUID, "
        "Optional[T], and list[T] for primitive T."
    )
    raise TypeError(msg)
