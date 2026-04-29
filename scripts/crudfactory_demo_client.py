from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class DemoResponse:
    """One HTTP exchange exported by the demo client."""

    name: str
    description: str
    method: str
    url: str
    status: int
    request_json: object | None
    response_json: object | None


class DemoClient:
    """Small standard-library JSON client for the generated DRF API."""

    def __init__(self, *, base_url: str, auth_header: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header
        self.responses: list[DemoResponse] = []

    def get(
        self,
        path: str,
        *,
        name: str,
        description: str,
        query: dict[str, object] | None = None,
    ) -> object | None:
        return self.request("GET", path, name=name, description=description, query=query)

    def post(
        self,
        path: str,
        payload: dict[str, object],
        *,
        name: str,
        description: str,
    ) -> object | None:
        return self.request("POST", path, payload, name=name, description=description)

    def put(
        self,
        path: str,
        payload: dict[str, object],
        *,
        name: str,
        description: str,
    ) -> object | None:
        return self.request("PUT", path, payload, name=name, description=description)

    def patch(
        self,
        path: str,
        payload: dict[str, object],
        *,
        name: str,
        description: str,
    ) -> object | None:
        return self.request("PATCH", path, payload, name=name, description=description)

    def delete(
        self,
        path: str,
        *,
        name: str,
        description: str,
    ) -> object | None:
        return self.request("DELETE", path, name=name, description=description)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        name: str,
        description: str,
        query: dict[str, object] | None = None,
    ) -> object | None:
        """Send one request and record the status/body even for HTTP errors."""
        url = self.build_url(path, query)
        body = encode_json(payload)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.auth_header is not None:
            headers["Authorization"] = self.auth_header
        request = Request(url, data=body, method=method, headers=headers)

        try:
            with urlopen(request, timeout=10) as response:
                status = response.status
                response_json = decode_json(response.read())
        except HTTPError as exc:
            status = exc.code
            response_json = decode_json(exc.read())

        self.responses.append(
            DemoResponse(
                name=name,
                description=description,
                method=method,
                url=url,
                status=status,
                request_json=payload,
                response_json=response_json,
            )
        )
        return response_json

    def build_url(
        self,
        path: str,
        query: dict[str, object] | None,
    ) -> str:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        return url


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise CRUDFactory's EV-only Django demo API and export JSON results."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    configure_django()
    auth_header = ensure_demo_admin_credentials()
    client = DemoClient(base_url=args.base_url, auth_header=auth_header)

    location_id = run_location_flow(client)
    chargepoint_id = run_chargepoint_flow(client, location_id)
    connector_id = run_connector_flow(client, chargepoint_id)
    run_connector_action_flow(client, connector_id)
    run_delete_flow(client, connector_id, chargepoint_id, location_id)
    run_schema_flow(client)

    export_results(client.responses, args.output_dir)
    print(f"Exported {len(client.responses)} HTTP exchanges.")
    return 0


def configure_django() -> None:
    """Set up Django so this client can seed the demo admin user and ACL data."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.django_project.settings")
    import django

    django.setup()


def ensure_demo_admin_credentials() -> str:
    """Ensure one demo admin user exists and return an HTTP Basic auth header."""
    from django.contrib.auth import get_user_model

    from crudfactory.models import AclEffect, AclGrant, AclPermission, AclSubjectKind

    user_model = get_user_model()
    username = "crudfactory-demo-admin"
    password = "crudfactory-demo-pass"
    user_manager = cast(Any, user_model.objects)
    user = user_manager.filter(username=username).first()
    if user is None:
        user = user_manager.create_user(username=username, password=password)
    else:
        user.set_password(password)
        user.save(update_fields=["password"])

    permission, _ = AclPermission.objects.get_or_create(
        permission_key="app.admin.full",
        defaults={
            "domain": "admin",
            "action": "full",
            "resource_type": "",
        },
    )
    AclGrant.objects.get_or_create(
        subject_kind=AclSubjectKind.USER,
        subject_user=user,
        permission=permission,
        effect=AclEffect.ALLOW,
    )
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def run_location_flow(client: DemoClient) -> int:
    """Exercise create/list/filter/detail/patch on `/locations/`."""
    created = require_dict(
        client.post(
            "/api/locations/",
            {
                "name": "Rome Central Hub",
                "city": "Rome",
                "address": "Via Roma 1",
                "postal_code": "00100",
                "country": "Italy",
            },
            name="01_locations_create",
            description="Create one EV location through the generated CRUD endpoint.",
        )
    )
    location_id = require_id(created)

    client.get(
        "/api/locations/",
        name="02_locations_list",
        description="List locations with embedded connector stats and capacity totals.",
    )
    client.get(
        "/api/locations/",
        query={"name__icontains": "rome", "ordering": "name"},
        name="03_locations_filter_order",
        description="Filter and order locations using DTO metadata.",
    )
    client.get(
        f"/api/locations/{location_id}/",
        name="04_locations_detail",
        description="Retrieve one location overview with embedded aggregate stats.",
    )
    client.patch(
        f"/api/locations/{location_id}/",
        {"city": "Rome Updated"},
        name="05_locations_patch",
        description="Patch one location field through the generated patch flow.",
    )
    return location_id


def run_chargepoint_flow(client: DemoClient, location_id: int) -> int:
    """Exercise create/detail/patch on `/chargepoints/`."""
    created = require_dict(
        client.post(
            "/api/chargepoints/",
            {
                "location_id": location_id,
                "name": "Rome CP 01",
                "serial_number": "ROME-CP-001",
                "software_version": "1.2.3",
                "vendor_name": "Open Charge",
                "max_power_kw": "180.00",
            },
            name="06_chargepoints_create",
            description="Create one chargepoint under the EV location.",
        )
    )
    chargepoint_id = require_id(created)

    client.get(
        f"/api/chargepoints/{chargepoint_id}/",
        name="07_chargepoints_detail",
        description="Retrieve one chargepoint with its nested connector list.",
    )
    client.patch(
        f"/api/chargepoints/{chargepoint_id}/",
        {"name": "Rome CP 01 Updated"},
        name="08_chargepoints_patch",
        description="Patch the chargepoint name through the restricted DTO contract.",
    )
    return chargepoint_id


def run_connector_flow(client: DemoClient, chargepoint_id: int) -> int:
    """Exercise connector CRUD and connector list filtering."""
    created = require_dict(
        client.post(
            "/api/connectors/",
            {
                "chargepoint_id": chargepoint_id,
                "name": "Connector A",
                "connector_type": "CCS",
                "status": "online",
                "is_locked": True,
                "power_kw": "120.00",
                "current_a": 250,
                "voltage_v": 400,
            },
            name="09_connectors_create",
            description="Create one connector on the chargepoint.",
        )
    )
    connector_id = require_id(created)

    client.get(
        "/api/connectors/",
        query={"status": "online", "ordering": "-power_kw"},
        name="10_connectors_list_filter_order",
        description="Filter and order connectors using DTO metadata.",
    )
    client.get(
        f"/api/connectors/{connector_id}/",
        name="11_connectors_detail",
        description="Retrieve connector detail with location and chargepoint context.",
    )
    client.put(
        f"/api/connectors/{connector_id}/",
        {
            "chargepoint_id": chargepoint_id,
            "name": "Connector A Updated",
            "connector_type": "CCS",
            "status": "online",
            "is_locked": True,
            "power_kw": "100.00",
            "current_a": 200,
            "voltage_v": 400,
        },
        name="12_connectors_update",
        description="Full update on the connector resource.",
    )
    return connector_id


def run_connector_action_flow(client: DemoClient, connector_id: int) -> None:
    """Exercise typed detail actions on `/connectors/{id}/.../`."""
    client.post(
        f"/api/connectors/{connector_id}/unlock/",
        {"reason": "remote reset"},
        name="13_connectors_unlock_action",
        description="Typed connector unlock action with DTO validation and ACL protection.",
    )
    client.post(
        f"/api/connectors/{connector_id}/start/",
        {"reason": "session begin"},
        name="14_connectors_start_action",
        description="Typed connector start action that transitions the status to occupied.",
    )
    client.post(
        f"/api/connectors/{connector_id}/stop/",
        {"reason": "session end"},
        name="15_connectors_stop_action",
        description="Typed connector stop action that returns the status to online.",
    )
    client.post(
        f"/api/connectors/{connector_id}/start/",
        {"reason": "x" * 81},
        name="16_connectors_action_validation_error",
        description="Validation failure on connector action DTO metadata.",
    )


def run_delete_flow(
    client: DemoClient,
    connector_id: int,
    chargepoint_id: int,
    location_id: int,
) -> None:
    """Delete the created EV resources in child-to-parent order."""
    client.delete(
        f"/api/connectors/{connector_id}/",
        name="17_connectors_delete",
        description="Delete the connector resource.",
    )
    client.delete(
        f"/api/chargepoints/{chargepoint_id}/",
        name="18_chargepoints_delete",
        description="Delete the chargepoint after its connector is gone.",
    )
    client.delete(
        f"/api/locations/{location_id}/",
        name="19_locations_delete",
        description="Delete the location after its chargepoint is gone.",
    )


def run_schema_flow(client: DemoClient) -> None:
    """Export the DRF Spectacular schema for the EV-only API surface."""
    client.get(
        "/schema/",
        name="20_openapi_schema",
        description="OpenAPI schema generated for the EV-only CRUDFactory routes.",
    )


def require_dict(value: object | None) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"Expected JSON object response, got {type(value).__name__}: {value!r}"
        raise RuntimeError(msg)
    return value


def require_id(value: dict[str, object]) -> int:
    raw_id = value.get("id")
    if not isinstance(raw_id, int):
        msg = f"Expected integer 'id' in response, got {raw_id!r}"
        raise RuntimeError(msg)
    return raw_id


def export_results(responses: list[DemoResponse], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    responses_dir = output_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    combined_path = output_dir / "crudfactory_demo_results.json"
    combined_payload = [
        response_to_dict(response, index)
        for index, response in enumerate(responses, start=1)
    ]
    combined_path.write_text(
        json.dumps(combined_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for index, response in enumerate(responses, start=1):
        individual_path = responses_dir / f"{index:02d}_{response.name}.json"
        individual_path.write_text(
            json.dumps(response_to_dict(response, index), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    export_schema_artifacts(responses, output_dir)
    export_factory_docs()


def response_to_dict(response: DemoResponse, index: int) -> dict[str, object]:
    return {
        "index": index,
        "name": response.name,
        "description": response.description,
        "method": response.method,
        "url": response.url,
        "status": response.status,
        "request_json": response.request_json,
        "response_json": response.response_json,
    }


def export_schema_artifacts(responses: list[DemoResponse], output_dir: Path) -> None:
    """Write standalone OpenAPI artifacts for quick local reference."""
    schema_response = next(
        (response for response in responses if response.name == "20_openapi_schema"),
        None,
    )
    if schema_response is None or not isinstance(schema_response.response_json, dict):
        return

    schema = schema_response.response_json
    openapi_json_path = output_dir / "ev_openapi_schema.json"
    openapi_json_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    generated_docs_dir = Path("wiki") / "generated"
    generated_docs_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = generated_docs_dir / "ev_openapi_summary.md"
    markdown_path.write_text(
        build_openapi_markdown(schema, openapi_json_path),
        encoding="utf-8",
    )


def export_factory_docs() -> None:
    """Write Markdown contract docs for the generated demo factories."""
    from tests.production_app.factories import (
        chargepoint_factory,
        chargepoint_summary_factory,
        connector_detail_factory,
        connector_factory,
        connector_summary_factory,
        location_detail_factory,
        location_factory,
        location_summary_factory,
    )

    generated_docs_dir = Path("wiki") / "generated" / "factories"
    generated_docs_dir.mkdir(parents=True, exist_ok=True)

    factories = [
        ("location-crud", "Location CRUD Factory", location_factory),
        ("chargepoint-crud", "Chargepoint CRUD Factory", chargepoint_factory),
        ("connector-crud", "Connector CRUD Factory", connector_factory),
        ("v3-station-summary", "V3 Station Summary Factory", location_summary_factory),
        ("v3-station-detail", "V3 Station Detail Factory", location_detail_factory),
        ("v3-chargepoint-summary", "V3 Chargepoint Summary Factory", chargepoint_summary_factory),
        ("v3-connector-summary", "V3 Connector Summary Factory", connector_summary_factory),
        ("v3-connector-detail", "V3 Connector Detail Factory", connector_detail_factory),
    ]

    index_lines = [
        "# Generated Factory Docs",
        "",
        "These files are generated from the CRUDFactory contracts used by the Django demo app.",
        "",
    ]
    for slug, title, factory in factories:
        output_path = generated_docs_dir / f"{slug}.md"
        output_path.write_text(
            factory.render_markdown_docs(title=title, base_path="/api"),
            encoding="utf-8",
        )
        index_lines.append(f"- [{title}](./factories/{slug}.md)")

    index_path = Path("wiki") / "generated" / "factory-docs-index.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def build_openapi_markdown(
    schema: dict[str, object],
    openapi_json_path: Path,
) -> str:
    """Return a short Markdown summary of the generated OpenAPI document."""
    title = stringify(schema.get("info", {}), "title", fallback="CRUDFactory EV Demo API")
    version = stringify(schema.get("info", {}), "version", fallback="unknown")
    paths = cast(dict[str, object], schema.get("paths", {}))

    lines = [
        f"# {title}",
        "",
        f"- Version: `{version}`",
        f"- OpenAPI JSON: [ev_openapi_schema.json](../../{openapi_json_path.as_posix()})",
        "",
        "## Routes",
        "",
    ]

    for path in sorted(paths):
        path_item = cast(dict[str, object], paths[path])
        lines.append(f"### `{path}`")
        lines.append("")
        for method in sorted(path_item):
            operation = cast(dict[str, object], path_item[method])
            summary = cast(str | None, operation.get("summary"))
            operation_id = cast(str | None, operation.get("operationId"))
            tags = operation.get("tags")
            tag_text = ""
            if isinstance(tags, list) and tags:
                tag_text = f" Tags: {', '.join(str(tag) for tag in tags)}."
            summary_text = summary or operation_id or "Generated operation"
            lines.append(
                f"- `{method.upper()}`: {summary_text}.{tag_text}"
            )
        lines.append("")

    return "\n".join(lines)


def stringify(container: object, key: str, *, fallback: str) -> str:
    """Return a string value from one mapping-like object."""
    if not isinstance(container, dict):
        return fallback
    value = container.get(key)
    if isinstance(value, str) and value:
        return value
    return fallback


def encode_json(payload: dict[str, object] | None) -> bytes | None:
    if payload is None:
        return None
    return json.dumps(payload).encode("utf-8")


def decode_json(data: bytes) -> object | None:
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
