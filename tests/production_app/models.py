from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models


class Supplier(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class InventoryItem(models.Model):
    name = models.CharField(max_length=80)
    quantity = models.PositiveIntegerField(default=0)
    internal_code = models.CharField(max_length=40, blank=True, default="")
    supplier = models.ForeignKey(
        Supplier,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="items",
    )

    class Meta:
        ordering = ["id"]

    if TYPE_CHECKING:
        supplier_id: int | None
        stock_level: StockLevel

    def __str__(self) -> str:
        return self.name


class StockLevel(models.Model):
    item = models.OneToOneField(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="stock_level",
    )
    warehouse_name = models.CharField(max_length=80)
    available = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.item.name}: {self.available} @ {self.warehouse_name}"


class StatusReading(models.Model):
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="status_readings",
    )
    state = models.CharField(max_length=20)
    duration = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.item.name}: {self.state} for {self.duration}"


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=160, blank=True, default="")
    network_name = models.CharField(max_length=120, blank=True, default="")
    active = models.BooleanField(default=True)
    city = models.CharField(max_length=80)
    address = models.CharField(max_length=160)
    postal_code = models.CharField(max_length=20)
    province = models.CharField(max_length=8, blank=True, default="")
    country = models.CharField(max_length=40, default="Italy")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]

    if TYPE_CHECKING:
        chargepoints: models.Manager[Chargepoint]

    def __str__(self) -> str:
        return self.name


class Chargepoint(models.Model):
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="chargepoints",
    )
    name = models.CharField(max_length=120)
    serial_number = models.CharField(max_length=80, unique=True)
    software_version = models.CharField(max_length=40)
    vendor_name = models.CharField(max_length=80, blank=True, default="")
    active = models.BooleanField(default=True)
    remote_ip = models.GenericIPAddressField(blank=True, null=True)
    ocpp_status = models.CharField(max_length=24, default="Offline")
    last_heartbeat = models.DateTimeField(blank=True, null=True)
    max_power_kw = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]

    if TYPE_CHECKING:
        location_id: int
        connectors: models.Manager[Connector]

    def __str__(self) -> str:
        return self.name


class Connector(models.Model):
    chargepoint = models.ForeignKey(
        Chargepoint,
        on_delete=models.CASCADE,
        related_name="connectors",
    )
    name = models.CharField(max_length=80)
    connector_type = models.CharField(max_length=40)
    status = models.CharField(max_length=20)
    is_locked = models.BooleanField(default=False)
    error_code = models.CharField(max_length=40, blank=True, default="")
    vendor_error_code = models.CharField(max_length=120, blank=True, default="")
    power_kw = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    current_a = models.PositiveIntegerField(default=0)
    voltage_v = models.PositiveIntegerField(default=0)
    stats = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]

    if TYPE_CHECKING:
        chargepoint_id: int

    def __str__(self) -> str:
        return self.name


class MonitoringStation(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["id"]

    if TYPE_CHECKING:
        hosts: models.Manager[MonitoringHost]

    def __str__(self) -> str:
        return self.name


class MonitoringHost(models.Model):
    station = models.ForeignKey(
        MonitoringStation,
        on_delete=models.CASCADE,
        related_name="hosts",
    )
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["id"]

    if TYPE_CHECKING:
        station_id: int
        items: models.Manager[MonitoringItem]

    def __str__(self) -> str:
        return self.name


class MonitoringItem(models.Model):
    itemid = models.AutoField(primary_key=True)
    host = models.ForeignKey(
        MonitoringHost,
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(max_length=120)
    units = models.CharField(max_length=40, blank=True, null=True)
    exclude_from_station_summary = models.BooleanField(default=False)

    class Meta:
        ordering = ["itemid"]

    if TYPE_CHECKING:
        host_id: int

    def __str__(self) -> str:
        return self.name
