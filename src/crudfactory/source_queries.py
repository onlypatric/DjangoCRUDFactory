from __future__ import annotations

from dataclasses import Field, dataclass, fields
from typing import Any, Sequence, cast

from .dataclass_serializers import ensure_dataclass_type
from .filters import (
    FilterDeclaration,
    FilterSpec,
    filter_declaration_from_metadata,
    filter_spec_for_lookup,
    normalize_filter_lookups,
)
from .ordering import OrderSpec, lookup_from_metadata

SOURCE_FILTER_METADATA_KEY = "crudfactory_source_filter"
SOURCE_ORDER_METADATA_KEY = "crudfactory_source_order"

__all__ = ["source_filterable", "source_orderable"]


@dataclass(frozen=True)
class SourceFilterDeclaration:
    """User-facing source filter metadata stored on a grouped query DTO field."""

    lookup: str | None
    lookups: tuple[str, ...]


def source_filterable(
    lookup: str | None = None,
    *,
    lookups: Sequence[str] = ("exact",),
) -> dict[str, object]:
    """Return metadata that marks a grouped action query field as source-filterable."""
    return {
        SOURCE_FILTER_METADATA_KEY: SourceFilterDeclaration(
            lookup=lookup,
            lookups=normalize_filter_lookups(lookups),
        )
    }


def source_orderable(lookup: str | None = None) -> dict[str, object]:
    """Return metadata that marks a grouped action query field as source-orderable."""
    return {SOURCE_ORDER_METADATA_KEY: lookup or True}


def source_filter_specs_from_dataclass(
    dataclass_type: type[object],
) -> tuple[FilterSpec, ...]:
    """Return source filter specs declared in one grouped query dataclass."""
    ensure_dataclass_type("grouped action query_dataclass", dataclass_type)
    specs: list[FilterSpec] = []
    for dataclass_field in fields(cast(Any, dataclass_type)):
        if SOURCE_FILTER_METADATA_KEY not in dataclass_field.metadata:
            continue
        metadata_value = dataclass_field.metadata[SOURCE_FILTER_METADATA_KEY]
        declaration = source_filter_declaration_from_metadata(
            dataclass_field.name,
            metadata_value,
        )
        specs.extend(
            filter_spec_for_lookup(
                field_name=dataclass_field.name,
                base_lookup=declaration.lookup or dataclass_field.name,
                lookup_name=lookup_name,
            )
            for lookup_name in declaration.lookups
        )
    return tuple(specs)


def source_order_specs_from_dataclass(
    dataclass_type: type[object],
) -> tuple[OrderSpec, ...]:
    """Return source order specs declared in one grouped query dataclass."""
    ensure_dataclass_type("grouped action query_dataclass", dataclass_type)
    return tuple(
        OrderSpec(
            query_name=dataclass_field.name,
            lookup=lookup_from_metadata(
                dataclass_field.name,
                dataclass_field.metadata[SOURCE_ORDER_METADATA_KEY],
            ),
        )
        for dataclass_field in fields(cast(Any, dataclass_type))
        if SOURCE_ORDER_METADATA_KEY in dataclass_field.metadata
    )


def source_filter_declaration_from_metadata(
    field_name: str,
    metadata_value: object,
) -> FilterDeclaration:
    """Normalize source filter metadata into the shared filter declaration shape."""
    if isinstance(metadata_value, SourceFilterDeclaration):
        return FilterDeclaration(
            lookup=metadata_value.lookup,
            lookups=metadata_value.lookups,
        )
    return filter_declaration_from_metadata(field_name, metadata_value)


def query_param_names_from_dataclass(dataclass_type: type[object]) -> set[str]:
    """Return exact-name query DTO parameters for one grouped action dataclass."""
    ensure_dataclass_type("grouped action query_dataclass", dataclass_type)
    return {
        dataclass_field.name
        for dataclass_field in fields(cast(Any, dataclass_type))
    }


def field_has_source_filter(dataclass_field: Field[Any]) -> bool:
    """Return True when a grouped query field opted into source filtering."""
    return SOURCE_FILTER_METADATA_KEY in dataclass_field.metadata


def field_has_source_order(dataclass_field: Field[Any]) -> bool:
    """Return True when a grouped query field opted into source ordering."""
    return SOURCE_ORDER_METADATA_KEY in dataclass_field.metadata
