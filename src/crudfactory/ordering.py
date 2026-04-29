from __future__ import annotations

from collections.abc import Mapping
from dataclasses import Field, dataclass, fields
from typing import Any, TypeVar, Callable, cast

from django.db import models
from rest_framework.exceptions import ValidationError

from .filters import response_dataclass_from_mapper

ORDER_METADATA_KEY = "crudfactory_order"
ORDERING_QUERY_PARAM = "ordering"

__all__ = ["orderable"]

ModelT = TypeVar("ModelT", bound=models.Model)


@dataclass(frozen=True)
class OrderSpec:
    """One response field that clients may use in the `ordering` query param."""

    query_name: str
    lookup: str


def orderable(lookup: str | None = None) -> dict[str, object]:
    """Return dataclass metadata that marks a response DTO field as orderable.

    Usage on a model-backed response field:
        name: str = field(metadata={**filterable(), **orderable()})

    Usage on a related/model-backed computed response field:
        supplier_name: str = field(metadata=orderable("supplier__name"))

    Clients can then request ascending or descending ordering:
        GET /items/?ordering=name
        GET /items/?ordering=-quantity,name
    """
    return {ORDER_METADATA_KEY: lookup or True}


def order_specs_from_response_mapper(
    response_mapper: Callable[..., object],
) -> tuple[OrderSpec, ...]:
    """Read ordering declarations from the response mapper's return dataclass."""
    response_type = response_dataclass_from_mapper(response_mapper)
    if response_type is None:
        return ()
    return order_specs_from_dataclass(response_type)


def order_specs_from_dataclass(dataclass_type: type[object]) -> tuple[OrderSpec, ...]:
    """Return ordering specs declared in dataclass field metadata."""
    return tuple(
        order_spec_from_field(dataclass_field)
        for dataclass_field in fields(cast(Any, dataclass_type))
        if field_is_orderable(dataclass_field)
    )


def field_is_orderable(dataclass_field: Field[object]) -> bool:
    """Return True when a response field opted into ordering."""
    return ORDER_METADATA_KEY in dataclass_field.metadata


def order_spec_from_field(dataclass_field: Field[object]) -> OrderSpec:
    """Convert one dataclass field metadata declaration into an OrderSpec."""
    metadata_value = dataclass_field.metadata[ORDER_METADATA_KEY]
    lookup = lookup_from_metadata(dataclass_field.name, metadata_value)
    return OrderSpec(query_name=dataclass_field.name, lookup=lookup)


def lookup_from_metadata(field_name: str, metadata_value: object) -> str:
    """Resolve order metadata into a Django ORM lookup string."""
    if metadata_value is True:
        return field_name
    if isinstance(metadata_value, str) and metadata_value:
        return metadata_value
    msg = (
        f"Invalid order metadata for {field_name!r}. "
        "Use orderable() or orderable('related__field')."
    )
    raise TypeError(msg)


def apply_order_specs(
    queryset: models.QuerySet[ModelT],
    query_params: Mapping[str, str],
    order_specs: tuple[OrderSpec, ...],
) -> models.QuerySet[ModelT]:
    """Apply user-requested ordering from the `ordering` query parameter."""
    requested_ordering = query_params.get(ORDERING_QUERY_PARAM)
    if not isinstance(requested_ordering, str) or not requested_ordering:
        return queryset

    allowed_ordering = allowed_ordering_by_query_name(order_specs)
    order_by_fields = order_by_fields_from_query_param(
        requested_ordering,
        allowed_ordering,
    )
    if not order_by_fields:
        return queryset
    return queryset.order_by(*order_by_fields)


def allowed_ordering_by_query_name(
    order_specs: tuple[OrderSpec, ...],
) -> dict[str, str]:
    """Return public ordering names mapped to Django ORM order_by fields."""
    return {order_spec.query_name: order_spec.lookup for order_spec in order_specs}


def order_by_fields_from_query_param(
    requested_ordering: str,
    allowed_ordering: dict[str, str],
) -> list[str]:
    """Parse and validate a comma-separated ordering query parameter."""
    requested_fields = [
        part.strip()
        for part in requested_ordering.split(",")
        if part.strip()
    ]
    return [
        order_by_field_from_requested_field(requested_field, allowed_ordering)
        for requested_field in requested_fields
    ]


def order_by_field_from_requested_field(
    requested_field: str,
    allowed_ordering: dict[str, str],
) -> str:
    """Return the Django order_by value for one public ordering field."""
    descending = requested_field.startswith("-")
    public_name = requested_field[1:] if descending else requested_field
    lookup = allowed_ordering.get(public_name)
    if lookup is None:
        allowed_names = ", ".join(sorted(allowed_ordering)) or "none"
        raise ValidationError(
            {
                "ordering": (
                    f"Unsupported ordering field {public_name!r}. "
                    f"Allowed fields: {allowed_names}."
                )
            }
        )
    if descending:
        return f"-{lookup}"
    return lookup
