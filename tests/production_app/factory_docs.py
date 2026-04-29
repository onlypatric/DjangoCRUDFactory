from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .factories import (
    chargepoint_detail_factory,
    chargepoint_factory,
    chargepoint_summary_factory,
    connector_detail_factory,
    connector_factory,
    connector_summary_factory,
    location_detail_factory,
    location_factory,
    location_summary_factory,
)


@dataclass(frozen=True)
class FactoryDocEntry:
    slug: str
    title: str
    factory: Any


FACTORY_DOCS: tuple[FactoryDocEntry, ...] = (
    FactoryDocEntry(
        slug="location-crud",
        title="Location CRUD Factory",
        factory=location_factory,
    ),
    FactoryDocEntry(
        slug="chargepoint-crud",
        title="Chargepoint CRUD Factory",
        factory=chargepoint_factory,
    ),
    FactoryDocEntry(
        slug="connector-crud",
        title="Connector CRUD Factory",
        factory=connector_factory,
    ),
    FactoryDocEntry(
        slug="v3-station-summary",
        title="V3 Station Summary Factory",
        factory=location_summary_factory,
    ),
    FactoryDocEntry(
        slug="v3-station-detail",
        title="V3 Station Detail Factory",
        factory=location_detail_factory,
    ),
    FactoryDocEntry(
        slug="v3-chargepoint-summary",
        title="V3 Chargepoint Summary Factory",
        factory=chargepoint_summary_factory,
    ),
    FactoryDocEntry(
        slug="v3-chargepoint-detail",
        title="V3 Chargepoint Detail Factory",
        factory=chargepoint_detail_factory,
    ),
    FactoryDocEntry(
        slug="v3-connector-summary",
        title="V3 Connector Summary Factory",
        factory=connector_summary_factory,
    ),
    FactoryDocEntry(
        slug="v3-connector-detail",
        title="V3 Connector Detail Factory",
        factory=connector_detail_factory,
    ),
)

FACTORY_DOCS_BY_SLUG = {entry.slug: entry for entry in FACTORY_DOCS}


def factory_docs_index_markdown(*, base_path: str = "/api") -> str:
    lines = [
        "# Factory Docs",
        "",
        "Generated live from the Django test server.",
        "",
    ]
    for entry in FACTORY_DOCS:
        lines.append(f"- [{entry.title}](./{entry.slug}/)")
    lines.append("")
    lines.append(f"- Base API path: `{base_path}`")
    return "\n".join(lines) + "\n"
