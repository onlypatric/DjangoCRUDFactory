from __future__ import annotations

from django.urls import path

from .factories import (
    ChargepointDetailViewSet,
    ChargepointSummaryViewSet,
    ConnectorDetailViewSet,
    ConnectorSummaryViewSet,
    LocationDetailViewSet,
    LocationSummaryViewSet,
    chargepoint_factory,
    connector_factory,
    location_factory,
    monitoring_item_factory,
)

app_name = location_factory.app_name
urlpatterns = [
    *location_factory.get_urlpatterns(),
    *chargepoint_factory.get_urlpatterns(),
    *connector_factory.get_urlpatterns(),
    *monitoring_item_factory.get_urlpatterns(),
    # These explicit V3 routes are compatibility endpoints. They sit on the
    # same models as the main CRUD API, but they deliberately expose different
    # response contracts and patch DTOs, so they are mounted separately instead
    # of sharing the default router-generated URLs.
    path(
        "v3/ocpp/stations/",
        LocationSummaryViewSet.as_view({"get": "list"}),
        name="v3-ocpp-station-list",
    ),
    path(
        "v3/ocpp/stations/<int:pk>/",
        LocationDetailViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="v3-ocpp-station-detail",
    ),
    path(
        "v3/ocpp/chargepoints/",
        ChargepointSummaryViewSet.as_view({"get": "list"}),
        name="v3-ocpp-chargepoint-list",
    ),
    path(
        "v3/ocpp/chargepoints/<int:pk>/",
        ChargepointDetailViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="v3-ocpp-chargepoint-detail",
    ),
    path(
        "v3/ocpp/connectors/",
        ConnectorSummaryViewSet.as_view({"get": "list"}),
        name="v3-ocpp-connector-list",
    ),
    path(
        "v3/ocpp/connectors/<int:pk>/",
        ConnectorDetailViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="v3-ocpp-connector-detail",
    ),
]
