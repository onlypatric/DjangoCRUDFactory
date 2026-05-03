from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from django.db import models
from django.db.models import Exists, OuterRef, Subquery

from crudfactory import (
    CRUDFactory,
    annotated_field,
    collection_action,
    filterable,
    latest_related_value,
    model_field,
    orderable,
    query_exclude,
    query_ordering,
    query_range,
    query_search,
)

from ..models import InventoryItem, StatusReading, StockLevel


LATEST_STATUS_READING = StatusReading.objects.filter(
    item=OuterRef("pk")
).order_by("-id")

INVENTORY_ITEM_QUERYSET = InventoryItem.objects.select_related("supplier").order_by("id")


@dataclass(frozen=True)
class InventoryItemResponseDTO:
    id: int = field(metadata=model_field("pk"))
    name: str = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    quantity: int = field(metadata=orderable())
    latest_state: str | None = field(
        metadata=latest_related_value(
            relation="status_readings",
            default=None,
            order_by="-id",
            value_field="state",
        )
    )
    latest_duration: int | None = field(
        metadata=latest_related_value(
            relation="status_readings",
            default=None,
            order_by="-id",
            value_field="duration",
        )
    )
    has_stock_level: bool = field(
        metadata=annotated_field(
            annotation=Exists(StockLevel.objects.filter(item=OuterRef("pk"))),
            default=False,
        )
    )


@dataclass(frozen=True)
class InventoryItemListQueryDTO:
    search: str | None = field(
        default=None,
        metadata=query_search("name", "internal_code", "supplier__name"),
    )
    min_quantity: int | None = field(
        default=None,
        metadata=query_range("quantity", op="gte"),
    )
    max_quantity: int | None = field(
        default=None,
        metadata=query_range("quantity", op="lte"),
    )
    exclude_name: str | None = field(
        default=None,
        metadata=query_exclude("name", op="icontains"),
    )
    sort: str | None = field(
        default=None,
        metadata=query_ordering("name", "quantity", latest_state="latest_state"),
    )


@dataclass(frozen=True)
class InventorySearchQueryDTO:
    name: str | None = None
    min_quantity: int | None = None


@dataclass(frozen=True)
class InventorySearchItemDTO:
    id: int
    name: str
    quantity: int
    latest_state: str | None


@dataclass(frozen=True)
class InventorySearchResponseDTO:
    total: int
    items: list[InventorySearchItemDTO]


def inventory_search(
    queryset: models.QuerySet[InventoryItem] | Sequence[InventoryItem],
    query: InventorySearchQueryDTO,
) -> InventorySearchResponseDTO:
    if isinstance(queryset, models.QuerySet):
        filtered_queryset = queryset
    else:
        item_ids = [item.pk for item in queryset if item.pk is not None]
        filtered_queryset = INVENTORY_ITEM_QUERYSET.filter(pk__in=item_ids)
    if query.name is not None:
        filtered_queryset = filtered_queryset.filter(name__icontains=query.name)
    if query.min_quantity is not None:
        filtered_queryset = filtered_queryset.filter(quantity__gte=query.min_quantity)
    items = list(
        filtered_queryset.annotate(
            latest_state=Subquery(LATEST_STATUS_READING.values("state")[:1])
        ).order_by("id")
    )
    return InventorySearchResponseDTO(
        total=len(items),
        items=[
            InventorySearchItemDTO(
                id=item.pk,
                name=item.name,
                quantity=item.quantity,
                latest_state=getattr(item, "latest_state", None),
            )
            for item in items
        ],
    )


inventory_item_factory = CRUDFactory.read_only(
    model=InventoryItem,
    response_dataclass=InventoryItemResponseDTO,
    queryset=INVENTORY_ITEM_QUERYSET,
    list_query=InventoryItemListQueryDTO,
    app_name="inventory",
    route="inventory-items",
    basename="inventory-item",
    custom_actions=(
        collection_action(
            name="search",
            query_dataclass=InventorySearchQueryDTO,
            response_dataclass=InventorySearchResponseDTO,
            handler=inventory_search,
            methods=("get",),
        ),
    ),
)
