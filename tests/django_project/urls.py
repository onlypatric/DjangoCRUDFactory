from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from tests.production_app.doc_views import (
    factory_docs_detail_view,
    factory_docs_index_view,
)

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/factories/", factory_docs_index_view, name="factory-docs-index"),
    path(
        "docs/factories/<slug:slug>/",
        factory_docs_detail_view,
        name="factory-docs-detail",
    ),
    path("api/", include("tests.production_app.urls", namespace="inventory")),
]
