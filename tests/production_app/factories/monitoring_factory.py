from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, cast

from django.db import models

from crudfactory import (
    ACLActionConfig,
    ACLConfig,
    ACLResourceRef,
    CRUDFactory,
    DjangoACLBackend,
    GroupedCollectionSourceACL,
    filterable,
    grouped_collection_action,
    model_field,
    orderable,
    source_filterable,
    source_orderable,
)

from ..models import MonitoringHost, MonitoringItem, MonitoringStation


MONITORING_ITEM_QUERYSET = MonitoringItem.objects.filter(
    exclude_from_station_summary=False
).select_related("host__station").order_by("host__station__name", "host__name", "itemid")


@dataclass(frozen=True)
class MonitoringItemResponseDTO:
    itemid: int = field(metadata={**model_field("itemid"), **orderable("itemid")})
    name: str = field(
        metadata={**filterable(lookups=("exact", "icontains")), **orderable()}
    )
    units: str | None
    host_id: int = field(metadata=model_field("host_id"))
    host_name: str = field(metadata=model_field("host__name"))
    station_id: int = field(metadata=model_field("host__station_id"))
    station_name: str = field(metadata=model_field("host__station__name"))


@dataclass(frozen=True)
class MonitoringStationSummaryQuery:
    station_name: str | None = field(
        default=None,
        metadata=source_filterable("host__station__name", lookups=("exact", "icontains")),
    )
    host_name: str | None = field(
        default=None,
        metadata=source_filterable("host__name", lookups=("exact", "icontains")),
    )
    item_name: str | None = field(
        default=None,
        metadata=source_filterable("name", lookups=("exact", "icontains")),
    )
    itemid: int | None = field(
        default=None,
        metadata=source_orderable("itemid"),
    )


@dataclass(frozen=True)
class MonitoringStationSummaryItemResponse:
    id: int
    name: str
    units: str | None


@dataclass(frozen=True)
class MonitoringStationSummaryHostResponse:
    id: int
    name: str
    items: list[MonitoringStationSummaryItemResponse]


@dataclass(frozen=True)
class MonitoringStationSummaryStationResponse:
    id: int
    name: str | None
    hosts: list[MonitoringStationSummaryHostResponse]


@dataclass(frozen=True)
class MonitoringStationSummaryCollectionResponse:
    stations: list[MonitoringStationSummaryStationResponse]


def monitoring_item_resource_ref(item: MonitoringItem) -> ACLResourceRef:
    return ACLResourceRef(
        "monitoring_item",
        f"monitoring_item:{item.itemid}",
    )


def group_items_by_station(
    items: models.QuerySet[MonitoringItem] | Sequence[MonitoringItem],
    _query: MonitoringStationSummaryQuery,
) -> MonitoringStationSummaryCollectionResponse:
    station_hosts: dict[
        int,
        tuple[MonitoringStation, dict[int, tuple[MonitoringHost, list[MonitoringItem]]]],
    ] = {}
    station_order: list[int] = []
    host_order_by_station: dict[int, list[int]] = {}

    for item in items:
        station = cast(MonitoringStation, item.host.station)
        host = cast(MonitoringHost, item.host)
        if station.pk not in station_hosts:
            station_hosts[station.pk] = (station, {})
            station_order.append(station.pk)
            host_order_by_station[station.pk] = []
        _, hosts = station_hosts[station.pk]
        if host.pk not in hosts:
            hosts[host.pk] = (host, [])
            host_order_by_station[station.pk].append(host.pk)
        hosts[host.pk][1].append(item)

    stations: list[MonitoringStationSummaryStationResponse] = []
    for station_id in station_order:
        station, hosts = station_hosts[station_id]
        host_responses: list[MonitoringStationSummaryHostResponse] = []
        for host_id in host_order_by_station[station_id]:
            host, host_items = hosts[host_id]
            host_responses.append(
                MonitoringStationSummaryHostResponse(
                    id=host_id,
                    name=host.name,
                    items=[
                        MonitoringStationSummaryItemResponse(
                            id=item.itemid,
                            name=item.name,
                            units=item.units,
                        )
                        for item in host_items
                    ],
                )
            )
        stations.append(
            MonitoringStationSummaryStationResponse(
                id=station_id,
                name=station.name,
                hosts=host_responses,
            )
        )
    return MonitoringStationSummaryCollectionResponse(stations=stations)


monitoring_item_factory = CRUDFactory.read_only(
    model=MonitoringItem,
    response_dataclass=MonitoringItemResponseDTO,
    queryset=MONITORING_ITEM_QUERYSET,
    route="monitoring-items",
    basename="monitoring-item",
    custom_actions=(),
    grouped_actions=(
        grouped_collection_action(
            name="station-summary",
            query_dataclass=MonitoringStationSummaryQuery,
            response_dataclass=MonitoringStationSummaryCollectionResponse,
            handler=group_items_by_station,
            source_acl=GroupedCollectionSourceACL(
                permission="app.monitoring.items.read",
                resource_ref_from_instance=monitoring_item_resource_ref,
            ),
        ),
    ),
    acl=cast(
        ACLConfig[MonitoringItem, object, object, object],
        ACLConfig(
            backend=DjangoACLBackend(),
            list_action=ACLActionConfig(permission="app.monitoring.items.read"),
            retrieve_action=ACLActionConfig(permission="app.monitoring.items.read"),
            resource_ref_from_instance=monitoring_item_resource_ref,
        ),
    ),
)
