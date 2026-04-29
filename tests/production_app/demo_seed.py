from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from crudfactory import ACLBootstrapper, ACLResourceRef
from crudfactory import ACLResourceSeed

from .models import Chargepoint, Connector, Location


@dataclass(frozen=True)
class DemoConnectorSeed:
    name: str
    connector_type: str
    status: str
    power_kw: Decimal
    current_a: int
    voltage_v: int
    is_locked: bool = False
    error_code: str = ""
    vendor_error_code: str = ""


@dataclass(frozen=True)
class DemoChargepointSeed:
    name: str
    serial_number: str
    software_version: str
    vendor_name: str
    max_power_kw: Decimal
    remote_ip: str
    ocpp_status: str
    connectors: tuple[DemoConnectorSeed, ...]


@dataclass(frozen=True)
class DemoLocationSeed:
    name: str
    description: str
    network_name: str
    city: str
    address: str
    postal_code: str
    province: str
    country: str
    chargepoints: tuple[DemoChargepointSeed, ...]


DEMO_LOCATIONS: tuple[DemoLocationSeed, ...] = (
    DemoLocationSeed(
        name="rome-hub",
        description="Primary fast-charging hub in Rome.",
        network_name="Voltis Roma",
        city="Rome",
        address="Via Ostiense 12",
        postal_code="00154",
        province="RM",
        country="Italy",
        chargepoints=(
            DemoChargepointSeed(
                name="Rome CP 01",
                serial_number="rome-hub/cp-01",
                software_version="3.2.0",
                vendor_name="Voltis",
                max_power_kw=Decimal("180.00"),
                remote_ip="10.20.0.11",
                ocpp_status="Available",
                connectors=(
                    DemoConnectorSeed(
                        name="connector-1",
                        connector_type="CCS",
                        status="online",
                        power_kw=Decimal("120.00"),
                        current_a=300,
                        voltage_v=400,
                    ),
                    DemoConnectorSeed(
                        name="connector-2",
                        connector_type="TYPE2",
                        status="faulted",
                        power_kw=Decimal("22.00"),
                        current_a=32,
                        voltage_v=400,
                        is_locked=True,
                        error_code="GroundFailure",
                    ),
                ),
            ),
            DemoChargepointSeed(
                name="Rome CP 02",
                serial_number="rome-hub/cp-02",
                software_version="3.1.4",
                vendor_name="Voltis",
                max_power_kw=Decimal("90.00"),
                remote_ip="10.20.0.12",
                ocpp_status="Charging",
                connectors=(
                    DemoConnectorSeed(
                        name="connector-1",
                        connector_type="CCS",
                        status="occupied",
                        power_kw=Decimal("90.00"),
                        current_a=220,
                        voltage_v=400,
                    ),
                ),
            ),
        ),
    ),
    DemoLocationSeed(
        name="milan-yard",
        description="Urban AC yard for fleet charging.",
        network_name="Voltis Milano",
        city="Milan",
        address="Via Stephenson 44",
        postal_code="20157",
        province="MI",
        country="Italy",
        chargepoints=(
            DemoChargepointSeed(
                name="Milan CP 01",
                serial_number="milan-yard/cp-01",
                software_version="2.9.7",
                vendor_name="GridFlow",
                max_power_kw=Decimal("44.00"),
                remote_ip="10.30.0.21",
                ocpp_status="Offline",
                connectors=(
                    DemoConnectorSeed(
                        name="connector-1",
                        connector_type="TYPE2",
                        status="offline",
                        power_kw=Decimal("22.00"),
                        current_a=32,
                        voltage_v=400,
                    ),
                    DemoConnectorSeed(
                        name="connector-2",
                        connector_type="TYPE2",
                        status="online",
                        power_kw=Decimal("22.00"),
                        current_a=32,
                        voltage_v=400,
                    ),
                ),
            ),
        ),
    ),
)


def seed_demo_locations(*, replace: bool = False) -> dict[str, int]:
    if replace:
        Connector.objects.all().delete()
        Chargepoint.objects.all().delete()
        Location.objects.all().delete()

    created_locations = 0
    created_chargepoints = 0
    created_connectors = 0

    for location_seed in DEMO_LOCATIONS:
        location, location_created = Location.objects.update_or_create(
            name=location_seed.name,
            defaults={
                "description": location_seed.description,
                "network_name": location_seed.network_name,
                "active": True,
                "city": location_seed.city,
                "address": location_seed.address,
                "postal_code": location_seed.postal_code,
                "province": location_seed.province,
                "country": location_seed.country,
                "metadata": {"source": "demo-seed"},
            },
        )
        if location_created:
            created_locations += 1

        for chargepoint_seed in location_seed.chargepoints:
            chargepoint, chargepoint_created = Chargepoint.objects.update_or_create(
                serial_number=chargepoint_seed.serial_number,
                defaults={
                    "location": location,
                    "name": chargepoint_seed.name,
                    "software_version": chargepoint_seed.software_version,
                    "vendor_name": chargepoint_seed.vendor_name,
                    "active": True,
                    "remote_ip": chargepoint_seed.remote_ip,
                    "ocpp_status": chargepoint_seed.ocpp_status,
                    "last_heartbeat": timezone.now(),
                    "max_power_kw": chargepoint_seed.max_power_kw,
                    "metadata": {"source": "demo-seed"},
                },
            )
            if chargepoint_created:
                created_chargepoints += 1

            for connector_seed in chargepoint_seed.connectors:
                connector, connector_created = Connector.objects.update_or_create(
                    chargepoint=chargepoint,
                    name=connector_seed.name,
                    defaults={
                        "connector_type": connector_seed.connector_type,
                        "status": connector_seed.status,
                        "is_locked": connector_seed.is_locked,
                        "error_code": connector_seed.error_code,
                        "vendor_error_code": connector_seed.vendor_error_code,
                        "power_kw": connector_seed.power_kw,
                        "current_a": connector_seed.current_a,
                        "voltage_v": connector_seed.voltage_v,
                        "stats": {
                            "sessions_today": 4 if connector_seed.status == "online" else 1,
                            "availability_pct": 97,
                        },
                        "metadata": {"source": "demo-seed"},
                    },
                )
                if connector_created:
                    created_connectors += 1

    seed_demo_acl_resources()
    return {
        "locations": created_locations,
        "chargepoints": created_chargepoints,
        "connectors": created_connectors,
    }


def seed_demo_acl_resources() -> None:
    bootstrapper = ACLBootstrapper()
    resource_seeds: list[ACLResourceSeed] = []
    for location in Location.objects.prefetch_related("chargepoints__connectors"):
        resource_seeds.append(
            ACLResourceSeed(
                resource_type="location",
                resource_key=location.name,
                display_name=location.name,
            )
        )
        for chargepoint in location.chargepoints.all():
            resource_seeds.append(
                ACLResourceSeed(
                    resource_type="chargepoint",
                    resource_key=chargepoint.serial_number,
                    display_name=chargepoint.name,
                    parent_ref=ACLResourceRef("location", location.name),
                )
            )
            for connector in chargepoint.connectors.all():
                resource_seeds.append(
                    ACLResourceSeed(
                        resource_type="connector",
                        resource_key=f"{chargepoint.serial_number}/{connector.name}",
                        display_name=connector.name,
                        parent_ref=ACLResourceRef(
                            "chargepoint",
                            chargepoint.serial_number,
                        ),
                    )
                )
    bootstrapper.ensure_resources(resource_seeds)
