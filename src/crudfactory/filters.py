from __future__ import annotations

from collections.abc import Mapping
from dataclasses import Field, dataclass, fields, is_dataclass
from typing import Any, TypeVar, Callable, Sequence, cast, get_type_hints

from django.db import models
from rest_framework.exceptions import ValidationError

FILTER_METADATA_KEY = "crudfactory_filter"
SUPPORTED_FILTER_LOOKUPS = frozenset(
    {
        "exact",
        "iexact",
        "contains",
        "icontains",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "isnull",
    }
)

__all__ = ["filterable"]

ModelT = TypeVar("ModelT", bound=models.Model)


@dataclass(frozen=True)
class FilterDeclaration:
    """User-facing filter metadata stored on one response dataclass field."""

    lookup: str | None
    lookups: tuple[str, ...]


@dataclass(frozen=True)
class FilterSpec:
    """One query parameter supported by a generated list endpoint.

    `query_param` is the public API name clients use in URLs.
    `lookup` is the Django ORM lookup applied to the underlying queryset.
    """

    query_param: str
    lookup: str
    value_parser: Callable[[str], object]


def filterable(
    lookup: str | None = None,
    *,
    lookups: Sequence[str] = ("exact",),
) -> dict[str, object]:
    """Return dataclass metadata that marks a response DTO field as filterable.

    Usage on a simple model-backed response field:
        name: str = field(metadata=filterable())

    Usage on a computed field backed by a related model:
        supplier_name: str = field(metadata=filterable("supplier__name"))

    Usage with richer lookup operators:
        name: str = field(metadata=filterable(lookups=("exact", "icontains")))
        quantity: int = field(metadata=filterable(lookups=("gte", "lte")))

    Returning metadata instead of wrapping `dataclasses.field` keeps the helper
    explicit and type-checker friendly.  Pyright/Pylance understand
    `dataclasses.field`, while CRUDFactory reads the metadata stored on it.
    """
    return {
        FILTER_METADATA_KEY: FilterDeclaration(
            lookup=lookup,
            lookups=normalize_filter_lookups(lookups),
        )
    }


def filter_specs_from_response_mapper(
    response_mapper: Callable[..., object],
) -> tuple[FilterSpec, ...]:
    """Read filter declarations from the response mapper's return dataclass.

    CRUDFactory keeps filter declarations close to the API response contract.
    The response mapper return annotation is therefore the bridge from factory
    configuration to the response DTO class.
    """
    response_type = response_dataclass_from_mapper(response_mapper)
    if response_type is None:
        return ()
    return filter_specs_from_dataclass(response_type)


def response_dataclass_from_mapper(
    response_mapper: Callable[..., object],
) -> type[object] | None:
    """Return the annotated response dataclass type, if one is available."""
    type_hints = get_type_hints(response_mapper)
    return_type = type_hints.get("return")
    if isinstance(return_type, type) and is_dataclass(return_type):
        return return_type
    return None


def filter_specs_from_dataclass(dataclass_type: type[object]) -> tuple[FilterSpec, ...]:
    """Return filter specs declared in dataclass field metadata."""
    specs: list[FilterSpec] = []
    for dataclass_field in fields(cast(Any, dataclass_type)):
        if field_is_filterable(dataclass_field):
            specs.extend(filter_specs_from_field(dataclass_field))
    return tuple(specs)


def field_is_filterable(dataclass_field: Field[object]) -> bool:
    """Return True when a response field opted into filtering."""
    return FILTER_METADATA_KEY in dataclass_field.metadata


def filter_specs_from_field(dataclass_field: Field[object]) -> tuple[FilterSpec, ...]:
    """Convert one dataclass field metadata declaration into filter specs."""
    metadata_value = dataclass_field.metadata[FILTER_METADATA_KEY]
    declaration = filter_declaration_from_metadata(dataclass_field.name, metadata_value)
    return tuple(
        filter_spec_for_lookup(
            field_name=dataclass_field.name,
            base_lookup=base_lookup_for_field(dataclass_field.name, declaration),
            lookup_name=lookup_name,
        )
        for lookup_name in declaration.lookups
    )


def filter_declaration_from_metadata(
    field_name: str,
    metadata_value: object,
) -> FilterDeclaration:
    """Resolve metadata into a normalized filter declaration."""
    if isinstance(metadata_value, FilterDeclaration):
        return metadata_value
    if metadata_value is True:
        return FilterDeclaration(lookup=None, lookups=("exact",))
    if isinstance(metadata_value, str) and metadata_value:
        return FilterDeclaration(lookup=metadata_value, lookups=("exact",))
    msg = (
        f"Invalid filter metadata for {field_name!r}. "
        "Use filterable(), filterable('related__field'), or "
        "filterable(lookups=('exact', 'icontains'))."
    )
    raise TypeError(msg)


def normalize_filter_lookups(lookups: Sequence[str]) -> tuple[str, ...]:
    """Return validated lookup operators for one filterable field."""
    normalized = tuple(lookups)
    if not normalized:
        msg = "filterable lookups must include at least one lookup operator."
        raise ValueError(msg)
    unsupported = sorted(set(normalized) - SUPPORTED_FILTER_LOOKUPS)
    if unsupported:
        msg = (
            "Unsupported filter lookup(s): "
            f"{', '.join(unsupported)}. "
            f"Supported lookups: {', '.join(sorted(SUPPORTED_FILTER_LOOKUPS))}."
        )
        raise ValueError(msg)
    return normalized


def base_lookup_for_field(
    field_name: str,
    declaration: FilterDeclaration,
) -> str:
    """Return the model lookup used before appending filter operators."""
    if declaration.lookup:
        return declaration.lookup
    return field_name


def filter_spec_for_lookup(
    *,
    field_name: str,
    base_lookup: str,
    lookup_name: str,
) -> FilterSpec:
    """Build one public query parameter for one allowed lookup operator."""
    if lookup_name == "exact":
        return FilterSpec(
            query_param=field_name,
            lookup=base_lookup,
            value_parser=parse_raw_filter_value,
        )
    return FilterSpec(
        query_param=f"{field_name}__{lookup_name}",
        lookup=f"{base_lookup}__{lookup_name}",
        value_parser=value_parser_for_lookup(lookup_name),
    )


def value_parser_for_lookup(lookup_name: str) -> Callable[[str], object]:
    """Return the parser needed before passing a query value to Django."""
    if lookup_name == "in":
        return parse_comma_separated_filter_value
    if lookup_name == "isnull":
        return parse_bool_filter_value
    return parse_raw_filter_value


def apply_filter_specs(
    queryset: models.QuerySet[ModelT],
    query_params: Mapping[str, str],
    filter_specs: tuple[FilterSpec, ...],
) -> models.QuerySet[ModelT]:
    """Apply declared filters from request query parameters."""
    filtered_queryset = queryset
    for filter_spec in filter_specs:
        filtered_queryset = apply_filter_spec(
            filtered_queryset,
            query_params,
            filter_spec,
        )
    return filtered_queryset


def apply_filter_spec(
    queryset: models.QuerySet[ModelT],
    query_params: Mapping[str, str],
    filter_spec: FilterSpec,
) -> models.QuerySet[ModelT]:
    """Apply one filter if the request includes its query parameter."""
    if filter_spec.query_param not in query_params:
        return queryset
    raw_value = query_params.get(filter_spec.query_param)
    if raw_value is None or not isinstance(raw_value, str):
        return queryset
    value = filter_spec.value_parser(raw_value)
    return queryset.filter(**{filter_spec.lookup: value})


def parse_raw_filter_value(value: str) -> str:
    """Return a query parameter value unchanged."""
    return value


def parse_comma_separated_filter_value(value: str) -> list[str]:
    """Parse `?field__in=a,b,c` into the list Django expects for `__in`."""
    return [part for part in value.split(",") if part]


def parse_bool_filter_value(value: str) -> bool:
    """Parse a boolean query parameter for Django's `isnull` lookup."""
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValidationError(
        {
            "detail": (
                "Invalid boolean filter value. Use true/false, 1/0, yes/no, or on/off."
            )
        }
    )
