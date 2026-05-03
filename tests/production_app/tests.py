from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from crudfactory import ACLBootstrapper, ACLResourceRef, DjangoACLBackend, DjangoACLService
from crudfactory.models import (
    AclEffect,
    AclGrant,
    AclGroup,
    AclGroupMember,
    AclPermission,
    AclResourceClosure,
    AclResourceNode,
    AclSubjectKind,
)
from rest_framework.test import APIClient

from .models import (
    Chargepoint,
    Connector,
    InventoryItem,
    Location,
    MonitoringHost,
    MonitoringItem,
    MonitoringStation,
    StatusReading,
    StockLevel,
    Supplier,
)


class ACLBootstrapCommandTests(TestCase):
    def test_bootstrap_acl_permissions_command_seeds_catalog(self) -> None:
        stdout = StringIO()

        call_command(
            "bootstrap_acl_permissions",
            "tests.production_app.acl_seed:ACL_PERMISSION_SEEDS",
            stdout=stdout,
        )

        self.assertTrue(
            AclPermission.objects.filter(permission_key="app.connector.start").exists()
        )
        self.assertTrue(
            AclPermission.objects.filter(permission_key="app.connector.unlock").exists()
        )
        self.assertIn("Created", stdout.getvalue())

    def test_bootstrap_acl_command_seeds_resources_and_grants(self) -> None:
        stdout = StringIO()

        call_command(
            "bootstrap_acl",
            "tests.production_app.acl_seed:bootstrap_acl_demo",
            stdout=stdout,
        )

        self.assertTrue(AclGroup.objects.filter(code="ops-admins").exists())
        self.assertTrue(
            AclResourceClosure.objects.filter(
                ancestor__resource_key="rome-hub/cp-01",
                descendant__resource_key="rome-hub/cp-01/connector-1",
                depth=1,
            ).exists()
        )
        self.assertTrue(
            AclGrant.objects.filter(
                permission__permission_key="app.connector.start",
                subject_group__code="ops-admins",
            ).exists()
        )
        self.assertIn("ACL bootstrap completed", stdout.getvalue())

    def test_bootstrap_acl_command_rejects_invalid_path_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "module.path:object_name"):
            call_command("bootstrap_acl", "not-a-valid-path")

    def test_acl_bootstrapper_rejects_resource_tree_cycles(self) -> None:
        bootstrapper = ACLBootstrapper()
        alpha = AclResourceNode.objects.create(resource_type="location", resource_key="alpha")
        beta = AclResourceNode.objects.create(
            resource_type="chargepoint",
            resource_key="beta",
            parent=alpha,
        )
        alpha.parent = beta
        alpha.save(update_fields=["parent"])

        with self.assertRaisesRegex(ValueError, "parent cycle"):
            bootstrapper.rebuild_resource_closure()


class DjangoACLServiceTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        user_manager = cast(Any, self.user_model.objects)
        self.user = user_manager.create_user("acl-user", password="test-pass")
        self.other_user = user_manager.create_user("acl-other", password="test-pass")
        self.group = AclGroup.objects.create(code="ops", name="Ops")
        self.service = DjangoACLService()
        self.permission("app.example.read", action="read", resource_type="connector")
        self.permission("app.example.write", action="write", resource_type="connector")
        self.permission("app.admin.full", action="full", resource_type="")

    def permission(self, permission_key: str, *, action: str, resource_type: str) -> AclPermission:
        return AclPermission.objects.create(
            permission_key=permission_key,
            domain="example",
            action=action,
            resource_type=resource_type,
        )

    def node(self, key: str, parent: AclResourceNode | None = None) -> AclResourceNode:
        node = AclResourceNode.objects.create(
            resource_type="connector",
            resource_key=key,
            parent=parent,
        )
        ancestors = [node] if parent is None else [node, parent]
        for depth, ancestor in enumerate(ancestors):
            AclResourceClosure.objects.create(ancestor=ancestor, descendant=node, depth=depth)
        return node

    def grant(
        self,
        *,
        permission_key: str,
        effect: str,
        user: Any = None,
        group: AclGroup | None = None,
        resource: AclResourceNode | None = None,
        enabled: bool = True,
    ) -> None:
        permission = AclPermission.objects.get(permission_key=permission_key)
        AclGrant.objects.create(
            subject_kind=AclSubjectKind.USER if user is not None else AclSubjectKind.GROUP,
            subject_user=user,
            subject_group=group,
            permission=permission,
            resource=resource,
            effect=effect,
            enabled=enabled,
        )

    def test_user_deny_beats_group_allow_globally(self) -> None:
        AclGroupMember.objects.create(group=self.group, user=self.user)
        self.grant(permission_key="app.example.read", effect=AclEffect.ALLOW, group=self.group)
        self.grant(permission_key="app.example.read", effect=AclEffect.DENY, user=self.user)

        self.assertFalse(self.service.has_permission(self.user, "app.example.read"))

    def test_scoped_grant_closer_than_global(self) -> None:
        root = self.node("root")
        leaf = self.node("leaf", parent=root)
        self.grant(permission_key="app.example.read", effect=AclEffect.ALLOW, user=self.user)
        self.grant(
            permission_key="app.example.read",
            effect=AclEffect.DENY,
            user=self.user,
            resource=leaf,
        )

        self.assertFalse(
            self.service.has_permission_on_resource(
                self.user,
                "app.example.read",
                ACLResourceRef("connector", "leaf"),
            )
        )

    def test_expired_group_membership_does_not_grant_permissions(self) -> None:
        AclGroupMember.objects.create(
            group=self.group,
            user=self.user,
            expires_at=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc),
        )
        self.grant(permission_key="app.example.read", effect=AclEffect.ALLOW, group=self.group)

        self.assertFalse(self.service.has_permission(self.user, "app.example.read"))

    def test_filter_allowed_resource_node_ids_handles_large_mixed_input(self) -> None:
        allowed_nodes = [self.node(f"allowed-{index}") for index in range(15)]
        denied_nodes = [self.node(f"denied-{index}") for index in range(15)]
        for node in allowed_nodes:
            self.grant(
                permission_key="app.example.read",
                effect=AclEffect.ALLOW,
                user=self.user,
                resource=node,
            )

        allowed_ids = self.service.filter_allowed_resource_node_ids(
            self.user,
            "app.example.read",
            [node.pk for node in allowed_nodes + denied_nodes],
        )

        self.assertEqual(allowed_ids, [node.pk for node in allowed_nodes])

    @override_settings(CRUDFACTORY={"ACL_ENABLED": False})
    def test_backend_returns_false_when_acl_is_disabled(self) -> None:
        permission = self.permission(
            "app.example.disabled",
            action="read",
            resource_type="connector",
        )
        del permission
        backend = DjangoACLBackend()

        self.assertFalse(backend.has_permission(self.user, "app.example.disabled"))


class EVInfrastructureCRUDIntegrationTests(TestCase):
    client: APIClient

    def setUp(self) -> None:
        self.client = APIClient()
        user_manager = cast(Any, get_user_model().objects)
        self.admin_user = user_manager.create_user("ev-admin", password="test-pass")
        admin_permission = AclPermission.objects.create(
            permission_key="app.admin.full",
            domain="admin",
            action="full",
            resource_type="",
        )
        AclGrant.objects.create(
            subject_kind=AclSubjectKind.USER,
            subject_user=self.admin_user,
            permission=admin_permission,
            effect=AclEffect.ALLOW,
        )
        self.client.force_authenticate(user=self.admin_user)

    def create_location(self, name: str = "Rome Central") -> Location:
        return Location.objects.create(
            name=name,
            description=f"{name} description",
            network_name="Voltis",
            active=True,
            city="Rome",
            address="Via Roma 1",
            postal_code="00100",
            province="RM",
            country="Italy",
            metadata={"source": "test"},
        )

    def create_chargepoint(
        self,
        *,
        location: Location,
        name: str = "CP Rome 1",
        serial_number: str = "ROME-CP-001",
    ) -> Chargepoint:
        return Chargepoint.objects.create(
            location=location,
            name=name,
            serial_number=serial_number,
            software_version="1.0.0",
            vendor_name="ACME",
            active=True,
            remote_ip="10.0.0.1",
            ocpp_status="Available",
            max_power_kw=Decimal("180.00"),
            metadata={"source": "test"},
        )

    def create_connector(
        self,
        *,
        chargepoint: Chargepoint,
        name: str = "Connector A",
        status: str = "online",
        is_locked: bool = False,
    ) -> Connector:
        return Connector.objects.create(
            chargepoint=chargepoint,
            name=name,
            connector_type="CCS",
            status=status,
            is_locked=is_locked,
            error_code="",
            vendor_error_code="",
            power_kw=Decimal("60.00"),
            current_a=150,
            voltage_v=400,
            stats={"sessions_today": 2},
            metadata={"source": "test"},
        )

    def create_inventory_item(self, name: str = "Boiler Sensor") -> InventoryItem:
        return InventoryItem.objects.create(
            name=name,
            quantity=12,
            internal_code=f"code-{name.lower().replace(' ', '-')}",
        )

    def test_location_endpoint_returns_connector_status_overview(self) -> None:
        location = self.create_location()
        chargepoint = self.create_chargepoint(location=location)
        self.create_connector(chargepoint=chargepoint, name="Connector A", status="online")
        self.create_connector(chargepoint=chargepoint, name="Connector B", status="faulted")

        list_response = self.client.get("/api/locations/", format="json")
        detail_response = self.client.get(
            reverse("inventory:location-detail", kwargs={"pk": location.pk}),
            format="json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.data["connector_status"],
            {"online": 1, "offline": 0, "faulted": 1, "occupied": 0},
        )
        self.assertEqual(
            detail_response.data["capacity"],
            {"chargepoints": 1, "connectors": 2, "total_power_kw": Decimal("120")},
        )

    def test_location_crud_lifecycle(self) -> None:
        create_response = self.client.post(
            "/api/locations/",
            {
                "name": "Milan North",
                "city": "Milan",
                "address": "Via Milano 20",
                "postal_code": "20100",
                "country": "Italy",
            },
            format="json",
        )
        detail_url = reverse(
            "inventory:location-detail",
            kwargs={"pk": create_response.data["id"]},
        )
        patch_response = self.client.patch(detail_url, {"city": "Turin"}, format="json")
        delete_response = self.client.delete(detail_url, format="json")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["city"], "Turin")
        self.assertEqual(delete_response.status_code, 204)

    def test_location_metadata_field_endpoint_reads_and_merges_json(self) -> None:
        location = self.create_location(name="Metadata Hub")

        get_response = self.client.get(
            f"/api/locations/{location.pk}/metadata/",
            format="json",
        )
        patch_response = self.client.patch(
            f"/api/locations/{location.pk}/metadata/",
            {"ui_color": "blue", "source": "patched"},
            format="json",
        )

        location.refresh_from_db()
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.data, {"source": "test"})
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(
            patch_response.data,
            {"source": "patched", "ui_color": "blue"},
        )
        self.assertEqual(location.metadata, {"source": "patched", "ui_color": "blue"})

    def test_chargepoint_returns_related_connectors_and_allows_name_patch(self) -> None:
        location = self.create_location(name="Naples Hub")
        create_response = self.client.post(
            "/api/chargepoints/",
            {
                "location_id": location.pk,
                "name": "South CP",
                "serial_number": "NAP-CP-01",
                "software_version": "2.5.1",
                "vendor_name": "Volt",
                "max_power_kw": "150.00",
                "connectors": [
                    {
                        "name": "North Plug",
                        "connector_type": "CCS",
                        "status": "online",
                        "is_locked": False,
                        "power_kw": "60.00",
                    },
                    {
                        "name": "South Plug",
                        "connector_type": "Type2",
                        "status": "occupied",
                        "is_locked": True,
                        "power_kw": "30.00",
                    },
                ],
            },
            format="json",
        )
        chargepoint = Chargepoint.objects.get(pk=create_response.data["id"])
        first_connector = chargepoint.connectors.order_by("id").first()
        self.assertIsNotNone(first_connector)
        connector = cast(Connector, first_connector)
        connector_id = cast(int, connector.pk)

        detail_response = self.client.get(
            reverse("inventory:chargepoint-detail", kwargs={"pk": chargepoint.pk}),
            format="json",
        )
        patch_response = self.client.patch(
            reverse("inventory:chargepoint-detail", kwargs={"pk": chargepoint.pk}),
            {
                "name": "South CP Updated",
                "connectors": [{"id": connector_id, "status": "faulted"}],
            },
            format="json",
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            [connector["is_locked"] for connector in detail_response.data["connectors"]],
            [False, True],
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["name"], "South CP Updated")
        self.assertEqual(
            sorted(connector["status"] for connector in patch_response.data["connectors"]),
            ["faulted", "occupied"],
        )

    def test_connector_full_crud_and_actions(self) -> None:
        location = self.create_location(name="Florence Hub")
        chargepoint = self.create_chargepoint(
            location=location,
            name="Florence CP",
            serial_number="FLO-CP-01",
        )
        create_response = self.client.post(
            "/api/connectors/",
            {
                "chargepoint_id": chargepoint.pk,
                "name": "Connector 1",
                "connector_type": "CCS",
                "status": "online",
                "is_locked": True,
                "power_kw": "120.00",
                "current_a": 250,
                "voltage_v": 400,
            },
            format="json",
        )
        connector_id = create_response.data["id"]
        detail_url = reverse("inventory:connector-detail", kwargs={"pk": connector_id})

        unlock_response = self.client.post(
            f"/api/connectors/{connector_id}/unlock/",
            {"reason": "remote reset"},
            format="json",
        )
        start_response = self.client.post(
            f"/api/connectors/{connector_id}/start/",
            {"reason": "session begin"},
            format="json",
        )
        stop_response = self.client.post(
            f"/api/connectors/{connector_id}/stop/",
            {"reason": "session end"},
            format="json",
        )
        update_response = self.client.put(
            detail_url,
            {
                "chargepoint_id": chargepoint.pk,
                "name": "Connector 1A",
                "connector_type": "CCS",
                "status": "online",
                "is_locked": False,
                "power_kw": "100.00",
                "current_a": 200,
                "voltage_v": 400,
            },
            format="json",
        )
        list_response = self.client.get(
            "/api/connectors/",
            {"status": "online", "ordering": "-power_kw"},
            format="json",
        )
        delete_response = self.client.delete(detail_url, format="json")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(unlock_response.data["is_locked"], False)
        self.assertEqual(start_response.data["status"], "occupied")
        self.assertEqual(stop_response.data["status"], "online")
        self.assertEqual(update_response.data["name"], "Connector 1A")
        self.assertEqual([item["name"] for item in list_response.data], ["Connector 1A"])
        self.assertEqual(delete_response.status_code, 204)

    def test_nested_connector_routes_stay_scoped_to_the_chargepoint(self) -> None:
        location = self.create_location(name="Nested Hub")
        first_chargepoint = self.create_chargepoint(
            location=location,
            name="Nested CP 1",
            serial_number="NEST-CP-01",
        )
        second_chargepoint = self.create_chargepoint(
            location=location,
            name="Nested CP 2",
            serial_number="NEST-CP-02",
        )
        kept_connector = self.create_connector(
            chargepoint=first_chargepoint,
            name="Scoped Connector",
            status="online",
        )
        hidden_connector = self.create_connector(
            chargepoint=second_chargepoint,
            name="Foreign Connector",
            status="faulted",
        )

        list_response = self.client.get(
            f"/api/chargepoints/{first_chargepoint.pk}/connectors/",
            {"ordering": "name"},
            format="json",
        )
        create_response = self.client.post(
            f"/api/chargepoints/{first_chargepoint.pk}/connectors/",
            {
                "chargepoint_id": second_chargepoint.pk,
                "name": "Bound Connector",
                "connector_type": "CCS",
                "status": "online",
                "is_locked": False,
                "power_kw": "22.00",
                "current_a": 32,
                "voltage_v": 400,
            },
            format="json",
        )
        detail_response = self.client.get(
            f"/api/chargepoints/{first_chargepoint.pk}/connectors/{hidden_connector.pk}/",
            format="json",
        )
        update_response = self.client.put(
            f"/api/chargepoints/{first_chargepoint.pk}/connectors/{kept_connector.pk}/",
            {
                "chargepoint_id": second_chargepoint.pk,
                "name": "Scoped Connector Updated",
                "connector_type": "CCS",
                "status": "offline",
                "is_locked": False,
                "power_kw": "30.00",
                "current_a": 40,
                "voltage_v": 400,
            },
            format="json",
        )

        kept_connector.refresh_from_db()
        created_connector = Connector.objects.get(pk=create_response.data["id"])
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            [item["name"] for item in list_response.data],
            ["Scoped Connector"],
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(created_connector.chargepoint_id, first_chargepoint.pk)
        self.assertEqual(create_response.data["chargepoint_id"], first_chargepoint.pk)
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(kept_connector.chargepoint_id, first_chargepoint.pk)
        self.assertEqual(kept_connector.name, "Scoped Connector Updated")

    def test_connector_bulk_operations_return_structured_results(self) -> None:
        location = self.create_location(name="Bulk Hub")
        chargepoint = self.create_chargepoint(
            location=location,
            name="Bulk CP",
            serial_number="BULK-CP-01",
        )

        bulk_create_response = self.client.post(
            "/api/connectors/bulk-create/",
            [
                {
                    "chargepoint_id": chargepoint.pk,
                    "name": "Bulk Connector 1",
                    "connector_type": "CCS",
                    "status": "online",
                    "is_locked": False,
                    "power_kw": "80.00",
                    "current_a": 200,
                    "voltage_v": 400,
                },
                {
                    "chargepoint_id": chargepoint.pk,
                    "name": "x",
                    "connector_type": "CCS",
                    "status": "online",
                    "is_locked": False,
                    "power_kw": "80.00",
                    "current_a": 200,
                    "voltage_v": 400,
                },
            ],
            format="json",
        )

        created_ids = [int(identifier) for identifier in bulk_create_response.data["succeeded_identifiers"]]
        bulk_patch_response = self.client.patch(
            "/api/connectors/bulk-patch/",
            [
                {"id": created_ids[0], "status": "faulted"},
            ],
            format="json",
        )
        bulk_delete_response = self.client.delete(
            "/api/connectors/bulk-delete/",
            [{"id": created_ids[0]}],
            format="json",
        )

        self.assertEqual(bulk_create_response.status_code, 200)
        self.assertEqual(bulk_create_response.data["created"], 1)
        self.assertEqual(bulk_create_response.data["failed"], 1)
        self.assertEqual(bulk_patch_response.status_code, 200)
        self.assertEqual(bulk_patch_response.data["updated"], 1)
        self.assertEqual(bulk_delete_response.status_code, 200)
        self.assertEqual(bulk_delete_response.data["deleted"], 1)

    def test_connector_start_rejects_locked_connector(self) -> None:
        location = self.create_location()
        chargepoint = self.create_chargepoint(location=location)
        connector = self.create_connector(
            chargepoint=chargepoint,
            name="Locked Connector",
            status="online",
            is_locked=True,
        )

        response = self.client.post(
            f"/api/connectors/{connector.pk}/start/",
            {"reason": "bad request"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_v3_ocpp_endpoints_use_same_ev_models(self) -> None:
        location = self.create_location(name="rome-hub")
        chargepoint = self.create_chargepoint(
            location=location,
            name="Rome CP 01",
            serial_number="rome-hub/cp-01",
        )
        chargepoint.ocpp_status = "Charging"
        chargepoint.save(update_fields=["ocpp_status"])
        connector = self.create_connector(
            chargepoint=chargepoint,
            name="connector-1",
            status="online",
        )

        station_list_response = self.client.get("/api/v3/ocpp/stations/", format="json")
        station_detail_response = self.client.get(
            f"/api/v3/ocpp/stations/{location.pk}/",
            format="json",
        )
        chargepoint_list_response = self.client.get(
            "/api/v3/ocpp/chargepoints/",
            format="json",
        )
        connector_detail_response = self.client.get(
            f"/api/v3/ocpp/connectors/{connector.pk}/",
            format="json",
        )
        station_patch_response = self.client.patch(
            f"/api/v3/ocpp/stations/{location.pk}/",
            {"description": "Updated v3 description"},
            format="json",
        )

        self.assertEqual(station_list_response.status_code, 200)
        self.assertEqual(station_list_response.data[0]["charge_network"], "Voltis")
        self.assertEqual(station_detail_response.status_code, 200)
        self.assertEqual(
            station_detail_response.data["chargepoints"][0]["serial_number"],
            "rome-hub/cp-01",
        )
        self.assertEqual(chargepoint_list_response.status_code, 200)
        self.assertEqual(chargepoint_list_response.data[0]["status"], "Charging")
        self.assertEqual(connector_detail_response.status_code, 200)
        self.assertEqual(
            connector_detail_response.data["serial_number"],
            "rome-hub/cp-01",
        )
        self.assertEqual(station_patch_response.status_code, 200)
        self.assertEqual(station_patch_response.data["description"], "Updated v3 description")

    def test_inventory_item_annotations_expose_latest_history_values(self) -> None:
        item = self.create_inventory_item()
        StatusReading.objects.create(item=item, state="online", duration=5)
        StatusReading.objects.create(item=item, state="faulted", duration=12)
        StockLevel.objects.create(
            item=item,
            warehouse_name="Main Warehouse",
            available=7,
        )

        list_response = self.client.get("/api/inventory-items/", format="json")
        detail_response = self.client.get(
            reverse("inventory:inventory-item-detail", kwargs={"pk": item.pk}),
            format="json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.data,
            {
                "id": item.pk,
                "name": "Boiler Sensor",
                "quantity": 12,
                "latest_state": "faulted",
                "latest_duration": 12,
                "has_stock_level": True,
            },
        )

    def test_inventory_item_query_collection_action_returns_typed_search_response(self) -> None:
        first = self.create_inventory_item(name="Boiler Sensor")
        first.quantity = 3
        first.save(update_fields=["quantity"])
        second = self.create_inventory_item(name="Boiler Alarm")
        second.quantity = 8
        second.save(update_fields=["quantity"])
        StatusReading.objects.create(item=first, state="offline", duration=2)
        StatusReading.objects.create(item=second, state="online", duration=7)

        response = self.client.get(
            "/api/inventory-items/search/?name=boiler&min_quantity=5",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "total": 1,
                "items": [
                    {
                        "id": second.pk,
                        "name": "Boiler Alarm",
                        "quantity": 8,
                        "latest_state": "online",
                    }
                ],
            },
        )

    def test_inventory_item_list_query_dto_filters_and_orders_collection_reads(self) -> None:
        supplier = Supplier.objects.create(name="Northwind")
        first = self.create_inventory_item(name="Boiler Sensor")
        first.quantity = 3
        first.internal_code = "alpha-1"
        first.supplier = supplier
        first.save(update_fields=["quantity", "internal_code", "supplier"])
        second = self.create_inventory_item(name="Boiler Alarm")
        second.quantity = 8
        second.internal_code = "alpha-2"
        second.save(update_fields=["quantity", "internal_code"])
        third = self.create_inventory_item(name="Pump")
        third.quantity = 12
        third.internal_code = "pump-1"
        third.save(update_fields=["quantity", "internal_code"])
        StatusReading.objects.create(item=first, state="offline", duration=2)
        StatusReading.objects.create(item=second, state="online", duration=7)
        StatusReading.objects.create(item=third, state="faulted", duration=4)

        response = self.client.get(
            "/api/inventory-items/?search=alpha&min_quantity=2&exclude_name=sensor&sort=-quantity",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["name"] for item in response.data],
            ["Boiler Alarm"],
        )

    def test_inventory_item_list_query_invalid_params_return_400(self) -> None:
        response = self.client.get(
            "/api/inventory-items/?min_quantity=invalid",
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("min_quantity", response.data)


class ConnectorACLIntegrationTests(TestCase):
    client: APIClient

    def setUp(self) -> None:
        self.client = APIClient()
        self.user_model = get_user_model()
        user_manager = cast(Any, self.user_model.objects)
        self.reader = user_manager.create_user("connector-reader", password="test-pass")
        self.operator = user_manager.create_user("connector-operator", password="test-pass")
        self.ensure_permissions()

    def ensure_permissions(self) -> None:
        for permission_key, action in (
            ("app.connector.read", "read"),
            ("app.connector.create", "create"),
            ("app.connector.update", "update"),
            ("app.connector.delete", "delete"),
            ("app.connector.start", "start"),
            ("app.connector.stop", "stop"),
            ("app.connector.unlock", "unlock"),
        ):
            AclPermission.objects.get_or_create(
                permission_key=permission_key,
                defaults={
                    "domain": "ev",
                    "action": action,
                    "resource_type": "connector",
                },
            )

    def create_connector_fixture(
        self,
        *,
        connector_name: str,
        serial_number: str,
    ) -> Connector:
        location = Location.objects.create(
            name=f"Location {serial_number}",
            description="ACL fixture location",
            network_name="ACL Grid",
            active=True,
            city="Rome",
            address="Via ACL 1",
            postal_code="00100",
            province="RM",
            country="Italy",
            metadata={"source": "acl-fixture"},
        )
        chargepoint = Chargepoint.objects.create(
            location=location,
            name=f"CP {serial_number}",
            serial_number=serial_number,
            software_version="1.0.0",
            vendor_name="ACL",
            active=True,
            remote_ip="10.1.0.1",
            ocpp_status="Available",
            max_power_kw=Decimal("60.00"),
            metadata={"source": "acl-fixture"},
        )
        connector = Connector.objects.create(
            chargepoint=chargepoint,
            name=connector_name,
            connector_type="CCS",
            status="online",
            is_locked=True,
            error_code="",
            vendor_error_code="",
            power_kw=Decimal("60.00"),
            current_a=150,
            voltage_v=400,
            stats={"sessions_today": 1},
            metadata={"source": "acl-fixture"},
        )
        self.ensure_resource_node(connector)
        return connector

    def ensure_resource_node(self, connector: Connector) -> None:
        location_node, _ = AclResourceNode.objects.get_or_create(
            resource_type="location",
            resource_key=connector.chargepoint.location.name,
        )
        chargepoint_node, _ = AclResourceNode.objects.get_or_create(
            resource_type="chargepoint",
            resource_key=connector.chargepoint.serial_number,
            defaults={"parent": location_node},
        )
        if chargepoint_node.parent is None or chargepoint_node.parent.pk != location_node.pk:
            chargepoint_node.parent = location_node
            chargepoint_node.save(update_fields=["parent"])
        connector_node, _ = AclResourceNode.objects.get_or_create(
            resource_type="connector",
            resource_key=self.connector_resource_key(connector),
            defaults={"parent": chargepoint_node},
        )
        if connector_node.parent is None or connector_node.parent.pk != chargepoint_node.pk:
            connector_node.parent = chargepoint_node
            connector_node.save(update_fields=["parent"])
        ACLBootstrapper().rebuild_resource_closure()

    def connector_resource_key(self, connector: Connector) -> str:
        return f"{connector.chargepoint.serial_number}/{connector.name}"

    def grant(self, user: Any, permission_key: str, connector: Connector) -> None:
        AclGrant.objects.create(
            subject_kind=AclSubjectKind.USER,
            subject_user=user,
            permission=AclPermission.objects.get(permission_key=permission_key),
            resource=AclResourceNode.objects.get(
                resource_type="connector",
                resource_key=self.connector_resource_key(connector),
            ),
            effect=AclEffect.ALLOW,
        )

    def test_connector_list_filters_unauthorized_resources(self) -> None:
        allowed = self.create_connector_fixture(
            connector_name="Allowed Connector",
            serial_number="ACL-CP-01",
        )
        self.create_connector_fixture(
            connector_name="Hidden Connector",
            serial_number="ACL-CP-02",
        )
        self.grant(self.reader, "app.connector.read", allowed)

        self.client.force_authenticate(user=self.reader)
        response = self.client.get("/api/connectors/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.data], ["Allowed Connector"])

    def test_connector_detail_returns_404_without_permission(self) -> None:
        connector = self.create_connector_fixture(
            connector_name="Hidden Connector",
            serial_number="ACL-CP-03",
        )

        self.client.force_authenticate(user=self.reader)
        response = self.client.get(
            reverse("inventory:connector-detail", kwargs={"pk": connector.pk}),
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_connector_actions_require_explicit_permissions(self) -> None:
        connector = self.create_connector_fixture(
            connector_name="Action Connector",
            serial_number="ACL-CP-04",
        )
        self.grant(self.operator, "app.connector.read", connector)
        self.grant(self.operator, "app.connector.unlock", connector)
        self.grant(self.operator, "app.connector.start", connector)
        self.grant(self.operator, "app.connector.stop", connector)

        self.client.force_authenticate(user=self.operator)
        unlock_response = self.client.post(
            f"/api/connectors/{connector.pk}/unlock/",
            {"reason": "manual release"},
            format="json",
        )
        start_response = self.client.post(
            f"/api/connectors/{connector.pk}/start/",
            {"reason": "session begin"},
            format="json",
        )
        stop_response = self.client.post(
            f"/api/connectors/{connector.pk}/stop/",
            {"reason": "session end"},
            format="json",
        )

        self.client.force_authenticate(user=self.reader)
        denied_response = self.client.post(
            f"/api/connectors/{connector.pk}/unlock/",
            {"reason": "manual release"},
            format="json",
        )

        self.assertEqual(unlock_response.status_code, 200)
        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(stop_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 404)

    def test_connector_metadata_field_endpoint_requires_read_and_update_permissions(self) -> None:
        connector = self.create_connector_fixture(
            connector_name="Metadata Connector",
            serial_number="ACL-CP-05",
        )
        self.grant(self.operator, "app.connector.read", connector)
        self.grant(self.operator, "app.connector.update", connector)

        self.client.force_authenticate(user=self.operator)
        get_response = self.client.get(
            f"/api/connectors/{connector.pk}/metadata/",
            format="json",
        )
        patch_response = self.client.patch(
            f"/api/connectors/{connector.pk}/metadata/",
            {"source": "patched", "visible": True},
            format="json",
        )

        self.client.force_authenticate(user=self.reader)
        denied_response = self.client.patch(
            f"/api/connectors/{connector.pk}/metadata/",
            {"source": "reader"},
            format="json",
        )

        connector.refresh_from_db()
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.data, {"source": "acl-fixture"})
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(
            patch_response.data,
            {"source": "patched", "visible": True},
        )
        self.assertEqual(connector.metadata, {"source": "patched", "visible": True})
        self.assertEqual(denied_response.status_code, 404)

    def test_connector_bulk_patch_reports_acl_row_denials(self) -> None:
        allowed = self.create_connector_fixture(
            connector_name="Allowed Connector",
            serial_number="ACL-CP-06",
        )
        denied = self.create_connector_fixture(
            connector_name="Denied Connector",
            serial_number="ACL-CP-07",
        )
        self.grant(self.operator, "app.connector.update", allowed)

        self.client.force_authenticate(user=self.operator)
        response = self.client.patch(
            "/api/connectors/bulk-patch/",
            [
                {"id": allowed.pk, "status": "faulted"},
                {"id": denied.pk, "status": "faulted"},
            ],
            format="json",
        )

        allowed.refresh_from_db()
        denied.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        self.assertEqual(response.data["failed"], 1)
        self.assertEqual(allowed.status, "faulted")
        self.assertEqual(denied.status, "online")


class MonitoringGroupedActionIntegrationTests(TestCase):
    client: APIClient

    def setUp(self) -> None:
        self.client = APIClient()
        user_manager = cast(Any, get_user_model().objects)
        self.reader = user_manager.create_user("monitor-reader", password="test-pass")
        AclPermission.objects.get_or_create(
            permission_key="app.monitoring.items.read",
            defaults={
                "domain": "monitoring",
                "action": "read",
                "resource_type": "monitoring_item",
            },
        )

    def create_monitoring_item(
        self,
        *,
        station_name: str,
        host_name: str,
        item_name: str,
        exclude_from_summary: bool = False,
    ) -> MonitoringItem:
        station, _ = MonitoringStation.objects.get_or_create(name=station_name)
        host, _ = MonitoringHost.objects.get_or_create(
            station=station,
            name=host_name,
        )
        item = MonitoringItem.objects.create(
            host=host,
            name=item_name,
            units="kW",
            exclude_from_station_summary=exclude_from_summary,
        )
        self.ensure_monitoring_resource_node(item)
        return item

    def ensure_monitoring_resource_node(self, item: MonitoringItem) -> None:
        station_node, _ = AclResourceNode.objects.get_or_create(
            resource_type="monitoring_station",
            resource_key=item.host.station.name,
        )
        host_node, _ = AclResourceNode.objects.get_or_create(
            resource_type="monitoring_host",
            resource_key=f"{item.host.station.name}/{item.host.name}",
            defaults={"parent": station_node},
        )
        if host_node.parent is None or host_node.parent.pk != station_node.pk:
            host_node.parent = station_node
            host_node.save(update_fields=["parent"])
        item_node, _ = AclResourceNode.objects.get_or_create(
            resource_type="monitoring_item",
            resource_key=f"monitoring_item:{item.itemid}",
            defaults={"parent": host_node},
        )
        if item_node.parent is None or item_node.parent.pk != host_node.pk:
            item_node.parent = host_node
            item_node.save(update_fields=["parent"])
        ACLBootstrapper().rebuild_resource_closure()

    def grant_read(self, item: MonitoringItem) -> None:
        AclGrant.objects.create(
            subject_kind=AclSubjectKind.USER,
            subject_user=self.reader,
            permission=AclPermission.objects.get(permission_key="app.monitoring.items.read"),
            resource=AclResourceNode.objects.get(
                resource_type="monitoring_item",
                resource_key=f"monitoring_item:{item.itemid}",
            ),
            effect=AclEffect.ALLOW,
        )

    def test_grouped_monitoring_endpoint_filters_by_acl_before_grouping(self) -> None:
        allowed = self.create_monitoring_item(
            station_name="Rome Station",
            host_name="Host A",
            item_name="Allowed Item",
        )
        self.create_monitoring_item(
            station_name="Rome Station",
            host_name="Host A",
            item_name="Hidden Item",
        )
        self.grant_read(allowed)

        self.client.force_authenticate(user=self.reader)
        response = self.client.get("/api/monitoring-items/station-summary/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "stations": [
                    {
                        "id": allowed.host.station_id,
                        "name": "Rome Station",
                        "hosts": [
                            {
                                "id": allowed.host_id,
                                "name": "Host A",
                                "items": [
                                    {
                                        "id": allowed.itemid,
                                        "name": "Allowed Item",
                                        "units": "kW",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        )

    def test_grouped_monitoring_endpoint_applies_source_filters_and_ordering(self) -> None:
        first = self.create_monitoring_item(
            station_name="Milan Station",
            host_name="Host Z",
            item_name="Alpha Item",
        )
        second = self.create_monitoring_item(
            station_name="Milan Station",
            host_name="Host Z",
            item_name="Alphabet Item",
        )
        hidden = self.create_monitoring_item(
            station_name="Milan Station",
            host_name="Host Z",
            item_name="Excluded Item",
            exclude_from_summary=True,
        )
        self.grant_read(first)
        self.grant_read(second)
        self.grant_read(hidden)

        self.client.force_authenticate(user=self.reader)
        response = self.client.get(
            "/api/monitoring-items/station-summary/?item_name__icontains=Alpha&ordering=-itemid",
            format="json",
        )

        items = response.data["stations"][0]["hosts"][0]["items"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in items], ["Alphabet Item", "Alpha Item"])
        self.assertNotIn("Excluded Item", [item["name"] for item in items])


class EVSeedCommandTests(TestCase):
    def test_seed_ev_demo_data_populates_models_and_acl_tree(self) -> None:
        stdout = StringIO()

        call_command("seed_ev_demo_data", "--replace", stdout=stdout)

        self.assertGreaterEqual(Location.objects.count(), 2)
        self.assertGreaterEqual(Chargepoint.objects.count(), 3)
        self.assertGreaterEqual(Connector.objects.count(), 5)
        self.assertTrue(
            AclResourceNode.objects.filter(
                resource_type="connector",
                resource_key="rome-hub/cp-01/connector-1",
            ).exists()
        )
        self.assertIn("Seeded EV demo data", stdout.getvalue())


class FactoryDocsServerTests(TestCase):
    def test_factory_docs_index_is_served_as_markdown(self) -> None:
        client = APIClient()

        response = client.get("/docs/factories/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("# Factory Docs", response.content.decode("utf-8"))
        self.assertIn("Location CRUD Factory", response.content.decode("utf-8"))

    def test_factory_detail_doc_is_generated_from_server(self) -> None:
        client = APIClient()

        response = client.get("/docs/factories/connector-crud/")

        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("# Connector CRUD Factory", body)
        self.assertIn("## Endpoints", body)
        self.assertIn("## Request DTOs", body)
        self.assertIn("## Response DTO", body)
        self.assertIn("## Field Subresource Endpoints", body)
        self.assertIn("## Bulk Operations", body)
        self.assertIn("`GET, PATCH /api/connectors/{pk}/metadata/`", body)
        self.assertIn("ConnectorActionInputDTO", body)
        self.assertIn("### `bulk_patch`", body)

    def test_inventory_factory_doc_mentions_query_collection_action(self) -> None:
        client = APIClient()

        response = client.get("/docs/factories/inventory-item-readonly/")

        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("### Advanced List Query DTO", body)
        self.assertIn("InventoryItemListQueryDTO", body)
        self.assertIn("### `search`", body)
        self.assertIn("- Query DTO:", body)
        self.assertIn("InventorySearchQueryDTO", body)

    def test_nested_connector_factory_doc_mentions_parent_scoped_route(self) -> None:
        client = APIClient()

        response = client.get("/docs/factories/chargepoint-connector-crud/")

        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "`GET /api/chargepoints/<int:chargepoint_pk>/connectors/`",
            body,
        )
