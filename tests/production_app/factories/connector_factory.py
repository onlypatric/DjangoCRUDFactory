from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import models
from rest_framework.exceptions import ValidationError

from crudfactory import (
    ACLActionConfig,
    ACLResourceRef,
    CRUDFactory,
    DjangoACLBackend,
    bulk_create_action,
    bulk_delete_action,
    bulk_patch_action,
    crud_acl,
    detail_action,
    field_subresource,
    filterable,
    length,
    model_field,
    orderable,
    range_,
    regex,
)

from ..models import Chargepoint, Connector


CONNECTOR_QUERYSET = Connector.objects.select_related("chargepoint__location").order_by("id")


@dataclass
class ConnectorCreateDTO:
    chargepoint_id: int = field(metadata={**model_field("chargepoint_id"), **range_(min=1)})
    name: str = field(metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=2, max=80)})
    connector_type: str = field(metadata=length(min=2, max=40))
    status: str = field(metadata=length(min=2, max=20))
    power_kw: Decimal = field(metadata=range_(min=0, max=500))
    current_a: int = field(metadata=range_(min=0, max=1000))
    voltage_v: int = field(metadata=range_(min=0, max=1000))
    is_locked: bool = False


@dataclass
class ConnectorUpdateDTO:
    chargepoint_id: int = field(metadata={**model_field("chargepoint_id"), **range_(min=1)})
    name: str = field(metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=2, max=80)})
    connector_type: str = field(metadata=length(min=2, max=40))
    status: str = field(metadata=length(min=2, max=20))
    power_kw: Decimal = field(metadata=range_(min=0, max=500))
    current_a: int = field(metadata=range_(min=0, max=1000))
    voltage_v: int = field(metadata=range_(min=0, max=1000))
    is_locked: bool = False


@dataclass
class ConnectorPatchDTO:
    chargepoint_id: int | None = field(
        default=None,
        metadata={**model_field("chargepoint_id"), **range_(min=1)},
    )
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=2, max=80)},
    )
    connector_type: str | None = field(default=None, metadata=length(min=2, max=40))
    status: str | None = field(default=None, metadata=length(min=2, max=20))
    is_locked: bool | None = None
    power_kw: Decimal | None = field(default=None, metadata=range_(min=0, max=500))
    current_a: int | None = field(default=None, metadata=range_(min=0, max=1000))
    voltage_v: int | None = field(default=None, metadata=range_(min=0, max=1000))


@dataclass
class ConnectorBulkPatchDTO:
    id: int = field(metadata=range_(min=1, max=999999))
    chargepoint_id: int | None = field(
        default=None,
        metadata={**model_field("chargepoint_id"), **range_(min=1)},
    )
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z0-9 -]+$"), **length(min=2, max=80)},
    )
    connector_type: str | None = field(default=None, metadata=length(min=2, max=40))
    status: str | None = field(default=None, metadata=length(min=2, max=20))
    is_locked: bool | None = None
    power_kw: Decimal | None = field(default=None, metadata=range_(min=0, max=500))
    current_a: int | None = field(default=None, metadata=range_(min=0, max=1000))
    voltage_v: int | None = field(default=None, metadata=range_(min=0, max=1000))


@dataclass
class ConnectorBulkDeleteDTO:
    id: int = field(metadata=range_(min=1, max=999999))


@dataclass
class ConnectorResponseDTO:
    id: int = field(metadata=model_field("pk"))
    chargepoint_id: int = field(metadata={**filterable(lookups=("exact",)), **orderable()})
    chargepoint_name: str = field(
        metadata={**model_field("chargepoint__name"), **filterable("chargepoint__name", lookups=("exact", "icontains")), **orderable("chargepoint__name")}
    )
    location_id: int = field(metadata=model_field("chargepoint__location_id"))
    location_name: str = field(
        metadata={**model_field("chargepoint__location__name"), **filterable("chargepoint__location__name", lookups=("exact", "icontains")), **orderable("chargepoint__location__name")}
    )
    name: str = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    connector_type: str
    status: str = field(metadata={**filterable(lookups=("exact",)), **orderable()})
    is_locked: bool
    power_kw: Decimal = field(metadata=orderable())
    current_a: int
    voltage_v: int


@dataclass
class ConnectorActionInputDTO:
    reason: str | None = field(default=None, metadata=length(max=80))


@dataclass
class ConnectorActionResponseDTO:
    id: int
    action: str
    status: str
    is_locked: bool
    message: str


# These `V3*` DTOs are the compatibility contract for the OCPP-style connector
# endpoints.
#
# They are kept next to the main connector CRUD types so the file documents the
# full surface area of the resource in one place:
# - modern CRUD contract
# - action DTOs
# - legacy summary/detail read models
# - legacy display-write DTO
@dataclass(frozen=True)
class V3ConnectorStatsResponse:
    sessions_today: int | None = None
    availability_pct: int | None = None


@dataclass(frozen=True)
class V3MetadataResponse:
    source: str | None = None


@dataclass(frozen=True)
class V3ConnectorSummaryResponse:
    id: int = field(metadata=model_field("pk"))
    nickname: str | None = field(
        metadata={**model_field("name"), **filterable("name", lookups=("exact", "icontains")), **orderable("name")}
    )
    chargepoint_id: int = field(metadata={**filterable(), **orderable()})
    status: str
    current_max: int = field(metadata={**model_field("current_a"), **filterable("current_a"), **orderable("current_a")})
    power_type: str = field(
        metadata={**model_field("connector_type", read_transform=lambda connector_type: ("DC" if connector_type.upper() == "DC" else "AC3" if connector_type.upper() in {"CCS", "CHADEMO"} else "AC1")), **filterable("connector_type", lookups=("exact", "icontains")), **orderable("connector_type")}
    )
    metadata: V3MetadataResponse = field(
        default_factory=V3MetadataResponse,
        metadata=model_field("metadata"),
    )


@dataclass(frozen=True)
class V3ConnectorDetailResponse:
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
class V3ConnectorDisplayWriteDTO:
    nickname: str | None = field(
        default=None,
        metadata={
            **model_field("name"),
            **length(min=1, max=128),
            **regex(r"^[A-Za-z0-9 _./()#+:,\-]+$"),
        },
    )


def connector_resource_ref(connector: Connector) -> ACLResourceRef:
    return ACLResourceRef(
        "connector",
        f"{connector.chargepoint.serial_number}/{connector.name}",
    )


def connector_resource_ref_from_chargepoint_and_name(
    chargepoint_id: int,
    connector_name: str,
) -> ACLResourceRef:
    chargepoint = Chargepoint.objects.get(pk=chargepoint_id)
    return ACLResourceRef("connector", f"{chargepoint.serial_number}/{connector_name}")


def connector_resource_ref_from_create(dto: ConnectorCreateDTO) -> ACLResourceRef:
    return connector_resource_ref_from_chargepoint_and_name(dto.chargepoint_id, dto.name)


def connector_resource_ref_from_update(
    _connector: Connector,
    dto: ConnectorUpdateDTO,
) -> ACLResourceRef:
    return connector_resource_ref_from_chargepoint_and_name(dto.chargepoint_id, dto.name)


def connector_resource_ref_from_patch(
    connector: Connector,
    dto: ConnectorPatchDTO,
) -> ACLResourceRef:
    return connector_resource_ref_from_chargepoint_and_name(
        dto.chargepoint_id or connector.chargepoint_id,
        dto.name or connector.name,
    )


def connector_action_response(
    connector: Connector,
    *,
    action: str,
    message: str,
) -> ConnectorActionResponseDTO:
    return ConnectorActionResponseDTO(
        id=connector.pk,
        action=action,
        status=connector.status,
        is_locked=connector.is_locked,
        message=message,
    )


def connector_action_suffix(dto: ConnectorActionInputDTO) -> str:
    return f" because {dto.reason}" if dto.reason else ""


def start_connector(
    connector: Connector,
    dto: ConnectorActionInputDTO,
) -> ConnectorActionResponseDTO:
    if connector.is_locked:
        raise ValidationError({"detail": "Locked connectors cannot be started."})
    if connector.status in {"offline", "faulted"}:
        raise ValidationError({"detail": "Only available connectors can be started."})
    connector.status = "occupied"
    connector.save(update_fields=["status"])
    return connector_action_response(
        connector,
        action="start",
        message=f"{connector.name} started{connector_action_suffix(dto)}.",
    )


def stop_connector(
    connector: Connector,
    dto: ConnectorActionInputDTO,
) -> ConnectorActionResponseDTO:
    if connector.status != "occupied":
        raise ValidationError({"detail": "Only occupied connectors can be stopped."})
    connector.status = "online"
    connector.save(update_fields=["status"])
    return connector_action_response(
        connector,
        action="stop",
        message=f"{connector.name} stopped{connector_action_suffix(dto)}.",
    )


def unlock_connector(
    connector: Connector,
    dto: ConnectorActionInputDTO,
) -> ConnectorActionResponseDTO:
    connector.is_locked = False
    connector.save(update_fields=["is_locked"])
    return connector_action_response(
        connector,
        action="unlock",
        message=f"{connector.name} unlocked{connector_action_suffix(dto)}.",
    )


connector_acl = crud_acl(
    backend=DjangoACLBackend(),
    permission_prefix="app.connector",
    resource_ref_from_instance=connector_resource_ref,
    resource_ref_from_create_input=connector_resource_ref_from_create,
    resource_ref_from_update_input=connector_resource_ref_from_update,
    resource_ref_from_patch_input=connector_resource_ref_from_patch,
)


connector_factory = CRUDFactory(
    model=Connector,
    response_dataclass=ConnectorResponseDTO,
    create_input=ConnectorCreateDTO,
    update_input=ConnectorUpdateDTO,
    partial_update_input=ConnectorPatchDTO,
    queryset=CONNECTOR_QUERYSET,
    field_subresources=[
        field_subresource(
            field_name="metadata",
            patch_mode="merge",
            read_permission="app.connector.read",
            update_permission="app.connector.update",
        )
    ],
    bulk_actions=[
        bulk_create_action(transaction_mode="best-effort"),
        bulk_patch_action(
            input_dataclass=ConnectorBulkPatchDTO,
            transaction_mode="best-effort",
        ),
        bulk_delete_action(
            input_dataclass=ConnectorBulkDeleteDTO,
            transaction_mode="best-effort",
        ),
    ],
    custom_actions=[
        detail_action(
            name="start",
            input_dataclass=ConnectorActionInputDTO,
            response_dataclass=ConnectorActionResponseDTO,
            handler=start_connector,
            acl=ACLActionConfig(
                permission="app.connector.start",
                mode="scoped",
                unauthorized_as_404=True,
            ),
        ),
        detail_action(
            name="stop",
            input_dataclass=ConnectorActionInputDTO,
            response_dataclass=ConnectorActionResponseDTO,
            handler=stop_connector,
            acl=ACLActionConfig(
                permission="app.connector.stop",
                mode="scoped",
                unauthorized_as_404=True,
            ),
        ),
        detail_action(
            name="unlock",
            input_dataclass=ConnectorActionInputDTO,
            response_dataclass=ConnectorActionResponseDTO,
            handler=unlock_connector,
            acl=ACLActionConfig(
                permission="app.connector.unlock",
                mode="scoped",
                unauthorized_as_404=True,
            ),
        ),
    ],
    acl=connector_acl,
    app_name="inventory",
    route="connectors",
    basename="connector",
)

# The V3 connector endpoints are intentionally split:
# - summary is list-friendly and compact
# - detail carries the richer compatibility payload for a single connector
#
# Two factories are easier to understand and evolve than one DTO with many
# optional fields that means different things in list and detail contexts.
connector_summary_factory = CRUDFactory.read_only(
    model=Connector,
    response_dataclass=V3ConnectorSummaryResponse,
    queryset=CONNECTOR_QUERYSET,
    app_name="inventory",
    route="v3/ocpp/connectors",
    basename="v3-connector-summary",
)

connector_detail_factory = CRUDFactory(
    model=Connector,
    response_dataclass=V3ConnectorDetailResponse,
    create_input=V3ConnectorDisplayWriteDTO,
    update_input=V3ConnectorDisplayWriteDTO,
    partial_update_input=V3ConnectorDisplayWriteDTO,
    queryset=CONNECTOR_QUERYSET,
    app_name="inventory",
    route="v3/ocpp/connectors",
    basename="v3-connector-detail",
)

ConnectorSummaryViewSet = connector_summary_factory.get_viewset_class()
ConnectorDetailViewSet = connector_detail_factory.get_viewset_class()
