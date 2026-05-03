from __future__ import annotations

from dataclasses import Field, MISSING, dataclass, field, fields, is_dataclass, make_dataclass
from enum import Enum
from typing import Any, Callable, Mapping, cast, get_type_hints

from django.db.models import Q

from .stats import count_stat

__all__ = ["enum_summary"]


@dataclass(frozen=True)
class EnumSummaryEntry:
    """One generated enum histogram field."""

    field_name: str
    match_value: object


def enum_summary(
    *,
    enum: type[Enum] | Mapping[str, object],
    lookup: str,
    value_field: str = "status",
    filter: Q | None = None,
    distinct: bool = False,
) -> Callable[[type[Any]], type[Any]]:
    """Generate count-stat fields from one enum-like value map.

    This decorator is applied *after* `@dataclass`. It replaces the dataclass
    with an equivalent one that contains one `count_stat(...)` field per enum
    member. The generated fields are normal dataclass fields, so the existing
    stats, schema, and Markdown-doc flows work without special cases.
    """

    enum_entries = normalize_enum_entries(enum)

    def decorate(dataclass_type: type[Any]) -> type[Any]:
        ensure_dataclass_type(dataclass_type)
        existing_fields = fields(dataclass_type)
        existing_names = {dataclass_field.name for dataclass_field in existing_fields}

        duplicate_names = [
            entry.field_name for entry in enum_entries if entry.field_name in existing_names
        ]
        if duplicate_names:
            raise TypeError(
                "enum_summary generated duplicate field names on "
                f"{dataclass_type.__name__}: {', '.join(repr(name) for name in duplicate_names)}."
            )

        type_hints = get_type_hints(dataclass_type)
        generated_fields = [
            (
                entry.field_name,
                int,
                count_stat(
                    count_lookup_for_enum_summary(lookup),
                    filter=combined_enum_filter(
                        base_filter=filter,
                        enum_lookup=enum_lookup_path(lookup=lookup, value_field=value_field),
                        match_value=entry.match_value,
                    ),
                    distinct=distinct,
                ),
            )
            for entry in enum_entries
        ]
        recreated_fields = [
            (
                dataclass_field.name,
                type_hints.get(dataclass_field.name, dataclass_field.type),
                cloned_dataclass_field(dataclass_field),
            )
            for dataclass_field in existing_fields
        ]
        namespace = preserved_namespace(dataclass_type)
        replacement = make_dataclass(
            cls_name=dataclass_type.__name__,
            fields=[*recreated_fields, *generated_fields],
            bases=dataclass_type.__bases__,
            namespace=namespace,
            init=dataclass_params_flag(dataclass_type, "init", True),
            repr=dataclass_params_flag(dataclass_type, "repr", True),
            eq=dataclass_params_flag(dataclass_type, "eq", True),
            order=dataclass_params_flag(dataclass_type, "order", False),
            unsafe_hash=dataclass_params_flag(dataclass_type, "unsafe_hash", False),
            frozen=dataclass_params_flag(dataclass_type, "frozen", False),
            match_args=dataclass_params_flag(dataclass_type, "match_args", True),
            kw_only=dataclass_params_flag(dataclass_type, "kw_only", False),
            slots=dataclass_params_flag(dataclass_type, "slots", False),
            weakref_slot=dataclass_params_flag(dataclass_type, "weakref_slot", False),
        )
        replacement.__module__ = dataclass_type.__module__
        replacement.__qualname__ = dataclass_type.__qualname__
        replacement.__doc__ = dataclass_type.__doc__
        setattr(
            replacement,
            "__crudfactory_enum_summary__",
            {
                "lookup": lookup,
                "value_field": value_field,
                "distinct": distinct,
                "values": {entry.field_name: entry.match_value for entry in enum_entries},
            },
        )
        return replacement

    return decorate


def ensure_dataclass_type(dataclass_type: type[Any]) -> None:
    if not is_dataclass(dataclass_type):
        raise TypeError("enum_summary must decorate a dataclass type.")


def normalize_enum_entries(
    enum: type[Enum] | Mapping[str, object],
) -> tuple[EnumSummaryEntry, ...]:
    if isinstance(enum, type) and issubclass(enum, Enum):
        return tuple(
            EnumSummaryEntry(
                field_name=normalized_enum_field_name(enum_member.name),
                match_value=enum_member.value,
            )
            for enum_member in enum
        )
    if isinstance(enum, Mapping):
        return tuple(
            EnumSummaryEntry(
                field_name=normalized_enum_field_name(field_name),
                match_value=match_value,
            )
            for field_name, match_value in enum.items()
        )
    raise TypeError("enum_summary enum must be an Enum subclass or mapping.")


def normalized_enum_field_name(raw_name: str) -> str:
    normalized = raw_name.strip().lower()
    for old, new in (("-", "_"), (" ", "_"), (".", "_"), ("/", "_")):
        normalized = normalized.replace(old, new)
    if not normalized.isidentifier():
        raise TypeError(f"enum_summary field name {raw_name!r} cannot be normalized into a valid identifier.")
    return normalized


def combined_enum_filter(
    *,
    base_filter: Q | None,
    enum_lookup: str,
    match_value: object,
) -> Q:
    value_filter = Q(**{enum_lookup: match_value})
    if base_filter is None:
        return value_filter
    return base_filter & value_filter


def count_lookup_for_enum_summary(lookup: str) -> str:
    if lookup.strip():
        return lookup
    return "pk"


def enum_lookup_path(*, lookup: str, value_field: str) -> str:
    if lookup.strip():
        return f"{lookup}__{value_field}"
    return value_field


def cloned_dataclass_field(dataclass_field: Field[Any]) -> Field[Any]:
    default_value = MISSING
    default_factory = MISSING
    if dataclass_field.default is not MISSING:
        default_value = dataclass_field.default
    if dataclass_field.default_factory is not MISSING:
        default_factory = dataclass_field.default_factory
    return cast(
        Field[Any],
        field(
            default=default_value,
            default_factory=default_factory,
            init=dataclass_field.init,
            repr=dataclass_field.repr,
            hash=dataclass_field.hash,
            compare=dataclass_field.compare,
            metadata=dict(dataclass_field.metadata),
            kw_only=getattr(dataclass_field, "kw_only", False),
        ),
    )


def preserved_namespace(dataclass_type: type[Any]) -> dict[str, object]:
    excluded_names = {
        "__dict__",
        "__doc__",
        "__hash__",
        "__match_args__",
        "__module__",
        "__slots__",
        "__weakref__",
        "__annotations__",
        "__dataclass_fields__",
        "__dataclass_params__",
        "__init__",
        "__setattr__",
        "__delattr__",
        "__repr__",
        "__eq__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
    }
    return {
        name: value
        for name, value in dataclass_type.__dict__.items()
        if name not in excluded_names
    }


def dataclass_params_flag(
    dataclass_type: type[Any],
    attribute_name: str,
    default: bool,
) -> bool:
    params = getattr(dataclass_type, "__dataclass_params__", None)
    if params is None:
        return default
    return cast(bool, getattr(params, attribute_name, default))
