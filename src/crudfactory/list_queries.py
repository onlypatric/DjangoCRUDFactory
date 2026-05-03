from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import Field, dataclass, fields
from typing import Any, TypeVar, cast

from django.db import models
from django.db.models import Q

from .dataclass_serializers import ensure_dataclass_type
from .filters import SUPPORTED_FILTER_LOOKUPS
from .ordering import order_by_field_from_requested_field

LIST_QUERY_FILTER_METADATA_KEY = "crudfactory_list_query_filter"
LIST_QUERY_SEARCH_METADATA_KEY = "crudfactory_list_query_search"
LIST_QUERY_ORDERING_METADATA_KEY = "crudfactory_list_query_ordering"

__all__ = [
    "query_exclude",
    "query_filter",
    "query_list",
    "query_ordering",
    "query_range",
    "query_search",
]

ModelT = TypeVar("ModelT", bound=models.Model)


@dataclass(frozen=True)
class ListQueryFilterDeclaration:
    lookup: str | None
    op: str
    exclude: bool = False


@dataclass(frozen=True)
class ListQuerySearchDeclaration:
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ListQueryOrderingDeclaration:
    allowed: dict[str, str]


@dataclass(frozen=True)
class ListQueryFilterSpec:
    field_name: str
    lookup: str
    exclude: bool = False


@dataclass(frozen=True)
class ListQuerySearchSpec:
    field_name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ListQueryOrderingSpec:
    field_name: str
    allowed: dict[str, str]


def query_filter(
    lookup: str | None = None,
    *,
    op: str = "exact",
) -> dict[str, object]:
    """Return metadata for one list-query DTO field that applies a queryset filter."""
    validate_query_lookup(op)
    return {
        LIST_QUERY_FILTER_METADATA_KEY: ListQueryFilterDeclaration(
            lookup=lookup,
            op=op,
        )
    }


def query_list(lookup: str | None = None) -> dict[str, object]:
    """Return metadata for one list-query DTO field that applies an `__in` filter."""
    return query_filter(lookup, op="in")


def query_range(
    lookup: str | None = None,
    *,
    op: str,
) -> dict[str, object]:
    """Return metadata for one list-query DTO field that applies a range filter."""
    if op not in {"gt", "gte", "lt", "lte"}:
        msg = "query_range op must be one of: gt, gte, lt, lte."
        raise ValueError(msg)
    return query_filter(lookup, op=op)


def query_exclude(
    lookup: str | None = None,
    *,
    op: str = "exact",
) -> dict[str, object]:
    """Return metadata for one list-query DTO field that applies a queryset exclude."""
    validate_query_lookup(op)
    return {
        LIST_QUERY_FILTER_METADATA_KEY: ListQueryFilterDeclaration(
            lookup=lookup,
            op=op,
            exclude=True,
        )
    }


def query_search(*fields_to_search: str) -> dict[str, object]:
    """Return metadata for a query field that does OR `icontains` search."""
    if not fields_to_search:
        msg = "query_search requires at least one target field."
        raise ValueError(msg)
    return {
        LIST_QUERY_SEARCH_METADATA_KEY: ListQuerySearchDeclaration(
            fields=tuple(fields_to_search)
        )
    }


def query_ordering(*allowed_fields: str, **field_lookups: str) -> dict[str, object]:
    """Return metadata for a query field that controls ordering."""
    allowed: dict[str, str] = {field_name: field_name for field_name in allowed_fields}
    allowed.update(field_lookups)
    if not allowed:
        msg = "query_ordering requires at least one allowed field."
        raise ValueError(msg)
    return {
        LIST_QUERY_ORDERING_METADATA_KEY: ListQueryOrderingDeclaration(
            allowed=allowed
        )
    }


def list_query_filter_specs_from_dataclass(
    dataclass_type: type[object],
) -> tuple[ListQueryFilterSpec, ...]:
    ensure_dataclass_type("list_query", dataclass_type)
    specs: list[ListQueryFilterSpec] = []
    for dataclass_field in fields(cast(Any, dataclass_type)):
        if LIST_QUERY_FILTER_METADATA_KEY not in dataclass_field.metadata:
            continue
        declaration = list_query_filter_declaration_from_field(dataclass_field)
        base_lookup = declaration.lookup or dataclass_field.name
        lookup = base_lookup if declaration.op == "exact" else f"{base_lookup}__{declaration.op}"
        specs.append(
            ListQueryFilterSpec(
                field_name=dataclass_field.name,
                lookup=lookup,
                exclude=declaration.exclude,
            )
        )
    return tuple(specs)


def list_query_search_specs_from_dataclass(
    dataclass_type: type[object],
) -> tuple[ListQuerySearchSpec, ...]:
    ensure_dataclass_type("list_query", dataclass_type)
    return tuple(
        ListQuerySearchSpec(
            field_name=dataclass_field.name,
            fields=list_query_search_declaration_from_field(dataclass_field).fields,
        )
        for dataclass_field in fields(cast(Any, dataclass_type))
        if LIST_QUERY_SEARCH_METADATA_KEY in dataclass_field.metadata
    )


def list_query_ordering_specs_from_dataclass(
    dataclass_type: type[object],
) -> tuple[ListQueryOrderingSpec, ...]:
    ensure_dataclass_type("list_query", dataclass_type)
    return tuple(
        ListQueryOrderingSpec(
            field_name=dataclass_field.name,
            allowed=dict(
                list_query_ordering_declaration_from_field(dataclass_field).allowed
            ),
        )
        for dataclass_field in fields(cast(Any, dataclass_type))
        if LIST_QUERY_ORDERING_METADATA_KEY in dataclass_field.metadata
    )


def list_query_param_names_from_dataclass(dataclass_type: type[object]) -> set[str]:
    ensure_dataclass_type("list_query", dataclass_type)
    return {
        dataclass_field.name
        for dataclass_field in fields(cast(Any, dataclass_type))
    }


def apply_list_query_dataclass(
    queryset: models.QuerySet[ModelT],
    dto: object,
    *,
    filter_specs: tuple[ListQueryFilterSpec, ...],
    search_specs: tuple[ListQuerySearchSpec, ...],
    ordering_specs: tuple[ListQueryOrderingSpec, ...],
) -> models.QuerySet[ModelT]:
    filtered_queryset = queryset
    for filter_spec in filter_specs:
        value = getattr(dto, filter_spec.field_name)
        if value is None or value == []:
            continue
        if filter_spec.exclude:
            filtered_queryset = filtered_queryset.exclude(**{filter_spec.lookup: value})
        else:
            filtered_queryset = filtered_queryset.filter(**{filter_spec.lookup: value})

    for search_spec in search_specs:
        value = getattr(dto, search_spec.field_name)
        if not isinstance(value, str) or not value:
            continue
        query = Q()
        for lookup in search_spec.fields:
            query |= Q(**{f"{lookup}__icontains": value})
        filtered_queryset = filtered_queryset.filter(query)

    order_by_fields: list[str] = []
    for ordering_spec in ordering_specs:
        value = getattr(dto, ordering_spec.field_name)
        order_by_fields.extend(order_by_fields_from_value(value, ordering_spec.allowed))
    if order_by_fields:
        filtered_queryset = filtered_queryset.order_by(*order_by_fields)
    return filtered_queryset


def order_by_fields_from_value(
    value: object,
    allowed_ordering: Mapping[str, str],
) -> list[str]:
    if value is None:
        return []
    requested_fields = requested_ordering_fields(value)
    return [
        order_by_field_from_requested_field(requested_field, dict(allowed_ordering))
        for requested_field in requested_fields
    ]


def requested_ordering_fields(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        requested_fields: list[str] = []
        for item in value:
            if isinstance(item, str):
                requested_fields.extend(
                    part.strip() for part in item.split(",") if part.strip()
                )
        return requested_fields
    return []


def list_query_filter_declaration_from_field(
    dataclass_field: Field[Any],
) -> ListQueryFilterDeclaration:
    metadata_value = dataclass_field.metadata[LIST_QUERY_FILTER_METADATA_KEY]
    if isinstance(metadata_value, ListQueryFilterDeclaration):
        return metadata_value
    msg = (
        f"Invalid list query filter metadata for {dataclass_field.name!r}. "
        "Use query_filter(), query_range(), query_list(), or query_exclude()."
    )
    raise TypeError(msg)


def list_query_search_declaration_from_field(
    dataclass_field: Field[Any],
) -> ListQuerySearchDeclaration:
    metadata_value = dataclass_field.metadata[LIST_QUERY_SEARCH_METADATA_KEY]
    if isinstance(metadata_value, ListQuerySearchDeclaration):
        return metadata_value
    msg = (
        f"Invalid list query search metadata for {dataclass_field.name!r}. "
        "Use query_search(...)."
    )
    raise TypeError(msg)


def list_query_ordering_declaration_from_field(
    dataclass_field: Field[Any],
) -> ListQueryOrderingDeclaration:
    metadata_value = dataclass_field.metadata[LIST_QUERY_ORDERING_METADATA_KEY]
    if isinstance(metadata_value, ListQueryOrderingDeclaration):
        return metadata_value
    msg = (
        f"Invalid list query ordering metadata for {dataclass_field.name!r}. "
        "Use query_ordering(...)."
    )
    raise TypeError(msg)


def validate_query_lookup(op: str) -> None:
    if op not in SUPPORTED_FILTER_LOOKUPS:
        msg = (
            f"Unsupported query lookup {op!r}. "
            f"Supported lookups: {', '.join(sorted(SUPPORTED_FILTER_LOOKUPS))}."
        )
        raise ValueError(msg)
