from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.db import models

from crudfactory import (
    CRUDFactory,
    filterable,
    length,
    model_field,
    nested_relation,
    orderable,
    range_,
    regex,
)

from ..models import Chargepoint


CHARGEPOINT_QUERYSET = Chargepoint.objects.select_related("location").prefetch_related(
    "connectors"
).order_by("id")


@dataclass
class ChargepointCreateDTO:
    location_id: int = field(metadata={**model_field("location_id"), **range_(min=1)})
    name: str = field(metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=3, max=120)})
    serial_number: str = field(metadata={**regex(r"^[A-Za-z0-9-]+$"), **length(min=4, max=80)})
    software_version: str = field(metadata=length(min=1, max=40))
    vendor_name: str = field(metadata=length(min=1, max=80))
    max_power_kw: Decimal = field(metadata=range_(min=0, max=500))
    connectors: list["ChargepointConnectorWriteDTO"] = field(default_factory=list)


@dataclass
class ChargepointUpdateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=3, max=120)})
    connectors: list["ChargepointConnectorNestedUpdateDTO"] | None = None


@dataclass
class ChargepointPatchDTO:
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=3, max=120)},
    )
    connectors: list["ChargepointConnectorNestedPatchDTO"] | None = None


@dataclass
class ChargepointConnectorWriteDTO:
    name: str = field(metadata=length(min=1, max=80))
    connector_type: str = field(metadata=length(min=1, max=40))
    status: str = field(metadata=length(min=1, max=20))
    is_locked: bool = False
    power_kw: Decimal = field(default=Decimal("0"), metadata=range_(min=0, max=500))


@dataclass
class ChargepointConnectorNestedUpdateDTO:
    id: int | None = field(default=None, metadata=range_(min=1))
    name: str | None = field(default=None, metadata=length(min=1, max=80))
    connector_type: str | None = field(default=None, metadata=length(min=1, max=40))
    status: str | None = field(default=None, metadata=length(min=1, max=20))
    is_locked: bool | None = None
    power_kw: Decimal | None = field(default=None, metadata=range_(min=0, max=500))


@dataclass
class ChargepointConnectorNestedPatchDTO:
    id: int | None = field(default=None, metadata=range_(min=1))
    name: str | None = field(default=None, metadata=length(min=1, max=80))
    connector_type: str | None = field(default=None, metadata=length(min=1, max=40))
    status: str | None = field(default=None, metadata=length(min=1, max=20))
    is_locked: bool | None = None
    power_kw: Decimal | None = field(default=None, metadata=range_(min=0, max=500))


@dataclass
class ChargepointConnectorDTO:
    id: int = field(metadata=model_field("pk"))
    name: str
    status: str
    is_locked: bool
    power_kw: Decimal


@dataclass
class ChargepointResponseDTO:
    id: int = field(metadata=model_field("pk"))
    location_id: int
    location_name: str = field(
        metadata={**model_field("location__name"), **filterable("location__name", lookups=("exact", "icontains")), **orderable("location__name")}
    )
    name: str = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    serial_number: str
    software_version: str
    vendor_name: str
    max_power_kw: Decimal
    connectors: list[ChargepointConnectorDTO] = field(
        default_factory=list,
        metadata=model_field("connectors"),
    )


# These `V3*` dataclasses define the legacy chargepoint contract that still
# exists for compatibility testing.
#
# They stay in this module on purpose so one file shows every public contract
# for the `Chargepoint` model:
# - the normal CRUD API
# - the summary compatibility API
# - the detail compatibility API
@dataclass(frozen=True)
class V3ConnectorStatsResponse:
    sessions_today: int | None = None
    availability_pct: int | None = None


@dataclass(frozen=True)
class V3MetadataResponse:
    source: str | None = None


@dataclass(frozen=True)
class V3ConnectorNestedResponse:
    id: int = field(metadata=model_field("pk"))
    nickname: str | None = field(metadata=model_field("name"))
    chargepoint_id: int
    status: str
    error_code: str | None
    vendor_error_code: str | None
    current_max: int = field(metadata=model_field("current_a"))
    power_type: str = field(
        metadata=model_field(
            "connector_type",
            read_transform=lambda connector_type: (
                "DC"
                if connector_type.upper() == "DC"
                else "AC3"
                if connector_type.upper() in {"CCS", "CHADEMO"}
                else "AC1"
            ),
        )
    )
    last_power_read: str | None = field(
        metadata=model_field("power_kw", read_transform=lambda power_kw: f"{power_kw}")
    )
    serial_number: str | None = field(metadata=model_field("chargepoint__serial_number"))
    last_energy_read: str | None = field(
        default=None,
        metadata=model_field("pk", read_transform=lambda _value: None),
    )
    stats: V3ConnectorStatsResponse = field(
        default_factory=V3ConnectorStatsResponse,
        metadata=model_field("stats"),
    )
    metadata: V3MetadataResponse = field(
        default_factory=V3MetadataResponse,
        metadata=model_field("metadata"),
    )


@dataclass(frozen=True)
class V3ChargepointSummaryResponse:
    id: int = field(metadata=model_field("pk"))
    name: str | None = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    serial_number: str | None = field(
        metadata={**filterable("serial_number", lookups=("exact", "icontains")), **orderable("serial_number")}
    )
    active: bool = field(metadata={**filterable(), **orderable()})
    remote_ip: str | None = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    status: str = field(metadata=model_field("ocpp_status"))
    updated_at: datetime | None = field(metadata=model_field("last_heartbeat"))
    station_id: int | None = field(
        metadata={**model_field("location_id"), **filterable("location_id"), **orderable("location_id")}
    )
    metadata: V3MetadataResponse = field(
        default_factory=V3MetadataResponse,
        metadata=model_field("metadata"),
    )


@dataclass(frozen=True)
class V3ChargepointDetailResponse:
    id: int = field(metadata=model_field("pk"))
    name: str | None
    serial_number: str | None
    active: bool
    remote_ip: str | None
    status: str = field(metadata=model_field("ocpp_status"))
    updated_at: datetime | None = field(metadata=model_field("last_heartbeat"))
    station_id: int | None = field(metadata=model_field("location_id"))
    connectors: list[V3ConnectorNestedResponse] = field(
        default_factory=list,
        metadata=model_field("connectors"),
    )
    metadata: V3MetadataResponse = field(
        default_factory=V3MetadataResponse,
        metadata=model_field("metadata"),
    )


@dataclass(frozen=True)
class V3ChargepointDisplayWriteDTO:
    name: str | None = field(
        default=None,
        metadata={**length(min=2, max=132), **regex(r"^[A-Za-z0-9 _./()#+:,\-]+$")},
    )


chargepoint_factory = CRUDFactory(
    model=Chargepoint,
    response_dataclass=ChargepointResponseDTO,
    create_input=ChargepointCreateDTO,
    update_input=ChargepointUpdateDTO,
    partial_update_input=ChargepointPatchDTO,
    nested_writes=[
        nested_relation(
            field_name="connectors",
            relation_name="connectors",
            mode="merge",
            match_by="id",
        )
    ],
    queryset=CHARGEPOINT_QUERYSET,
    app_name="inventory",
    route="chargepoints",
    basename="chargepoint",
)

# The legacy V3 surface uses different payloads for list and detail endpoints.
# Keeping them as separate factories keeps each response contract narrow and
# frontend-oriented instead of forcing one DTO to satisfy both.
chargepoint_summary_factory = CRUDFactory.read_only(
    model=Chargepoint,
    response_dataclass=V3ChargepointSummaryResponse,
    queryset=CHARGEPOINT_QUERYSET,
    app_name="inventory",
    route="v3/ocpp/chargepoints",
    basename="v3-chargepoint-summary",
)

chargepoint_detail_factory = CRUDFactory(
    model=Chargepoint,
    response_dataclass=V3ChargepointDetailResponse,
    create_input=V3ChargepointDisplayWriteDTO,
    update_input=V3ChargepointDisplayWriteDTO,
    partial_update_input=V3ChargepointDisplayWriteDTO,
    queryset=CHARGEPOINT_QUERYSET,
    app_name="inventory",
    route="v3/ocpp/chargepoints",
    basename="v3-chargepoint-detail",
)

ChargepointSummaryViewSet = chargepoint_summary_factory.get_viewset_class()
ChargepointDetailViewSet = chargepoint_detail_factory.get_viewset_class()
