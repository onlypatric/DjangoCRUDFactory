from __future__ import annotations

from django.urls.resolvers import URLPattern, URLResolver
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ModelViewSet

__all__: list[str] = []


def build_router(
    *,
    viewset_class: type[ModelViewSet],
    route: str,
    basename: str,
    router_class: type[SimpleRouter] = SimpleRouter,
) -> SimpleRouter:
    """Create a DRF router and register one generated ViewSet on it."""
    router = router_class()
    router.register(route, viewset_class, basename=basename)
    return router


def router_urlpatterns(router: SimpleRouter) -> list[URLPattern | URLResolver]:
    """Return router URLs as a plain list for Django `urlpatterns` usage."""
    return list(router.urls)


def build_app_urlconf(
    *,
    urlpatterns: list[URLPattern | URLResolver],
    app_name: str,
    namespace: str,
) -> tuple[list[URLPattern | URLResolver], str, str]:
    """Return the tuple shape accepted by `django.urls.include`."""
    return (urlpatterns, app_name, namespace)
