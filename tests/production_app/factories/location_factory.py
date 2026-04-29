from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.db import models

from crudfactory import CRUDFactory, count_stat, filterable, length, model_field, orderable, regex, sum_stat

from ..models import Location


LOCATION_QUERYSET = Location.objects.prefetch_related("chargepoints__connectors").order_by("id")
V3_LOCATION_QUERYSET = Location.objects.filter(active=True).prefetch_related(
    "chargepoints__connectors"
).order_by("name", "id")


@dataclass
class LocationCreateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=3, max=120)})
    city: str = field(metadata={**regex(r"^[A-Za-z -]+$"), **length(min=2, max=80)})
    address: str = field(metadata=length(min=5, max=160))
    postal_code: str = field(metadata=length(min=3, max=20))
    country: str = field(metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=40)})
    description: str = field(default="", metadata=length(max=160))
    province: str = field(default="", metadata=length(max=8))
    network_name: str = field(default="", metadata=length(max=120))


@dataclass
class LocationUpdateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=3, max=120)})
    city: str = field(metadata={**regex(r"^[A-Za-z -]+$"), **length(min=2, max=80)})
    address: str = field(metadata=length(min=5, max=160))
    postal_code: str = field(metadata=length(min=3, max=20))
    country: str = field(metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=40)})
    description: str = field(default="", metadata=length(max=160))
    province: str = field(default="", metadata=length(max=8))
    network_name: str = field(default="", metadata=length(max=120))


@dataclass
class LocationPatchDTO:
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=3, max=120)},
    )
    city: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z -]+$"), **length(min=2, max=80)},
    )
    address: str | None = field(default=None, metadata=length(min=5, max=160))
    postal_code: str | None = field(default=None, metadata=length(min=3, max=20))
    country: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=40)},
    )
    description: str | None = field(default=None, metadata=length(max=160))
    province: str | None = field(default=None, metadata=length(max=8))
    network_name: str | None = field(default=None, metadata=length(max=120))


@dataclass
class LocationConnectorStatusDTO:
    online: int = count_stat(
        "chargepoints__connectors",
        filter=models.Q(chargepoints__connectors__status="online"),
    )
    offline: int = count_stat(
        "chargepoints__connectors",
        filter=models.Q(chargepoints__connectors__status="offline"),
    )
    faulted: int = count_stat(
        "chargepoints__connectors",
        filter=models.Q(chargepoints__connectors__status="faulted"),
    )
    occupied: int = count_stat(
        "chargepoints__connectors",
        filter=models.Q(chargepoints__connectors__status="occupied"),
    )


@dataclass
class LocationCapacityStatsDTO:
    chargepoints: int = count_stat("chargepoints", distinct=True)
    connectors: int = count_stat("chargepoints__connectors", distinct=True)
    total_power_kw: Decimal = sum_stat(
        "chargepoints__connectors__power_kw",
        default=Decimal("0"),
    )


@dataclass
class LocationResponseDTO:
    id: int = field(metadata=model_field("pk"))
    name: str = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    city: str = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    address: str
    postal_code: str
    country: str
    connector_status: LocationConnectorStatusDTO = field(
        default_factory=LocationConnectorStatusDTO
    )
    capacity: LocationCapacityStatsDTO = field(default_factory=LocationCapacityStatsDTO)


# The `V3*` types below model the legacy OCPP-facing station API that the test
# project still exposes under `/api/v3/ocpp/stations/...`.
#
# They are intentionally kept in the same module as the main `Location` CRUD
# factory because they are two public contracts over the same Django model.
# Keeping them together makes it obvious which modern CRUD endpoint and which
# compatibility endpoint belong to the same resource.
@dataclass(frozen=True)
class V3MetadataResponse:
    source: str | None = None


@dataclass(frozen=True)
class V3ConnectorStatsResponse:
    sessions_today: int | None = None
    availability_pct: int | None = None


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
class V3LocationAddressResponse:
    address: str | None
    zip_code: str | None = field(metadata=model_field("postal_code"))
    city: str | None
    province: str | None


@dataclass(frozen=True)
class V3LocationChargepointStatsResponse:
    total: int = count_stat("chargepoints", distinct=True)
    available: int = count_stat(
        "chargepoints",
        filter=models.Q(chargepoints__ocpp_status="Available"),
        distinct=True,
    )
    charging: int = count_stat(
        "chargepoints",
        filter=models.Q(chargepoints__ocpp_status="Charging"),
        distinct=True,
    )
    unavailable: int = count_stat(
        "chargepoints",
        filter=models.Q(chargepoints__ocpp_status="Unavailable"),
        distinct=True,
    )
    faulted: int = count_stat(
        "chargepoints",
        filter=models.Q(chargepoints__ocpp_status="Faulted"),
        distinct=True,
    )
    offline: int = count_stat(
        "chargepoints",
        filter=models.Q(chargepoints__ocpp_status="Offline"),
        distinct=True,
    )


@dataclass(frozen=True)
class V3LocationSummaryResponse:
    id: int = field(metadata=model_field("pk"))
    name: str | None = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    description: str | None = field(
        metadata=filterable(lookups=("exact", "icontains"))
    )
    charge_network: str | None = field(
        metadata={**model_field("network_name"), **filterable("network_name", lookups=("exact", "icontains")), **orderable("network_name")}
    )
    active: bool = field(metadata={**filterable(), **orderable()})
    city: str | None = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    province: str | None = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    location: V3LocationAddressResponse = field(
        default_factory=lambda: V3LocationAddressResponse(None, None, None, None)
    )
    chargepoint_statuses: V3LocationChargepointStatsResponse = field(
        default_factory=V3LocationChargepointStatsResponse
    )
    metadata: V3MetadataResponse = field(
        default_factory=V3MetadataResponse,
        metadata=model_field("metadata"),
    )


@dataclass(frozen=True)
class V3LocationDetailChargepointResponse:
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
class V3LocationDetailResponse:
    id: int = field(metadata=model_field("pk"))
    name: str | None
    description: str | None
    charge_network: str | None = field(metadata=model_field("network_name"))
    active: bool
    location: V3LocationAddressResponse = field(
        default_factory=lambda: V3LocationAddressResponse(None, None, None, None)
    )
    chargepoints: list[V3LocationDetailChargepointResponse] = field(
        default_factory=list,
        metadata=model_field("chargepoints"),
    )
    metadata: V3MetadataResponse = field(
        default_factory=V3MetadataResponse,
        metadata=model_field("metadata"),
    )


@dataclass(frozen=True)
class V3LocationDisplayWriteDTO:
    name: str | None = field(
        default=None,
        metadata={**length(min=2, max=128), **regex(r"^[A-Za-z0-9 _./()#+:,\-]+$")},
    )
    description: str | None = field(default=None, metadata=length(max=160))
    address: str | None = field(
        default=None,
        metadata={**length(max=160), **regex(r"^[A-Za-z0-9 _./()#+:,\-]*$")},
    )
    city: str | None = field(
        default=None,
        metadata={**length(max=80), **regex(r"^[A-Za-z0-9 '._()/#+:,\-]*$")},
    )
    province: str | None = field(default=None, metadata=regex(r"^[A-Za-z]{0,8}$"))
    postal_code: str | None = field(
        default=None,
        metadata={**length(max=20), **regex(r"^[A-Za-z0-9 \-]*$")},
    )


location_factory = CRUDFactory(
    model=Location,
    response_dataclass=LocationResponseDTO,
    create_input=LocationCreateDTO,
    update_input=LocationUpdateDTO,
    partial_update_input=LocationPatchDTO,
    queryset=LOCATION_QUERYSET,
    app_name="inventory",
    route="locations",
    basename="location",
)

# These V3 factories intentionally split the compatibility surface into two
# separate read models:
# - a compact summary payload for station lists
# - a richer detail payload for station detail screens and display edits
#
# Using two factories is clearer than making one oversized DTO serve both use
# cases.
location_summary_factory = CRUDFactory.read_only(
    model=Location,
    response_dataclass=V3LocationSummaryResponse,
    queryset=V3_LOCATION_QUERYSET,
    app_name="inventory",
    route="v3/ocpp/stations",
    basename="v3-station-summary",
)

location_detail_factory = CRUDFactory(
    model=Location,
    response_dataclass=V3LocationDetailResponse,
    create_input=V3LocationDisplayWriteDTO,
    update_input=V3LocationDisplayWriteDTO,
    partial_update_input=V3LocationDisplayWriteDTO,
    queryset=V3_LOCATION_QUERYSET,
    app_name="inventory",
    route="v3/ocpp/stations",
    basename="v3-station-detail",
)

LocationSummaryViewSet = location_summary_factory.get_viewset_class()
LocationDetailViewSet = location_detail_factory.get_viewset_class()
