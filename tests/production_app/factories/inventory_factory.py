from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Exists, OuterRef, Subquery

from crudfactory import CRUDFactory, annotated_field, filterable, model_field, orderable

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
        metadata=annotated_field(
            annotation=Subquery(LATEST_STATUS_READING.values("state")[:1]),
            default=None,
        )
    )
    latest_duration: int | None = field(
        metadata=annotated_field(
            annotation=Subquery(LATEST_STATUS_READING.values("duration")[:1]),
            default=None,
        )
    )
    has_stock_level: bool = field(
        metadata=annotated_field(
            annotation=Exists(StockLevel.objects.filter(item=OuterRef("pk"))),
            default=False,
        )
    )


inventory_item_factory = CRUDFactory.read_only(
    model=InventoryItem,
    response_dataclass=InventoryItemResponseDTO,
    queryset=INVENTORY_ITEM_QUERYSET,
    app_name="inventory",
    route="inventory-items",
    basename="inventory-item",
)
