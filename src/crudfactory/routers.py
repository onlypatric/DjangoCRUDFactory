from __future__ import annotations

from typing import Any, cast

from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ModelViewSet

from .actions import CustomActionSpec, GroupedCollectionActionSpec
from .bulk_actions import BulkActionSpec
from .field_subresources import FieldSubresourceSpec

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


def nested_viewset_urlpatterns(
    *,
    viewset_class: type[ModelViewSet],
    route: str,
    basename: str,
    lookup_url_kwarg: str,
    parent_prefix: str,
    read_only: bool,
    custom_actions: tuple[CustomActionSpec[Any], ...],
    grouped_actions: tuple[GroupedCollectionActionSpec[Any], ...],
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    field_subresources: tuple[FieldSubresourceSpec, ...],
) -> list[URLPattern | URLResolver]:
    """Return manual urlpatterns for one parent-scoped generated ViewSet."""
    normalized_parent_prefix = parent_prefix.strip("/")
    normalized_route = route.strip("/")
    collection_path = f"{normalized_parent_prefix}/{normalized_route}/"
    detail_path = f"{collection_path}<path:{lookup_url_kwarg}>/"
    urlpatterns: list[URLPattern | URLResolver] = [
        path(
            collection_path,
            viewset_class.as_view(cast(Any, collection_actions_for_mode(read_only))),
            name=f"{basename}-list",
        ),
        path(
            detail_path,
            viewset_class.as_view(cast(Any, detail_actions_for_mode(read_only))),
            name=f"{basename}-detail",
        ),
    ]
    for custom_action in custom_actions:
        action_name = custom_action.name
        action_methods = {method.lower(): action_name for method in custom_action.methods}
        if custom_action.detail:
            action_path = f"{detail_path}{custom_action.url_path or action_name}/"
            url_name = custom_action.url_name or action_name
            urlpatterns.append(
                path(
                    action_path,
                    viewset_class.as_view(cast(Any, action_methods)),
                    name=f"{basename}-{url_name}",
                )
            )
            continue
        action_path = f"{collection_path}{custom_action.url_path or action_name}/"
        url_name = custom_action.url_name or action_name
        urlpatterns.append(
            path(
                action_path,
                viewset_class.as_view(cast(Any, action_methods)),
                name=f"{basename}-{url_name}",
            )
        )
    for grouped_action in grouped_actions:
        action_path = f"{collection_path}{grouped_action.url_path or grouped_action.name}/"
        url_name = grouped_action.url_name or grouped_action.name
        urlpatterns.append(
            path(
                action_path,
                viewset_class.as_view(cast(
                    Any,
                    {method.lower(): grouped_action.name for method in grouped_action.methods}
                )),
                name=f"{basename}-{url_name}",
            )
        )
    for bulk_action in bulk_actions:
        action_path = f"{collection_path}{bulk_action.url_path or bulk_action.name}/"
        url_name = bulk_action.url_name or bulk_action.name
        urlpatterns.append(
            path(
                action_path,
                viewset_class.as_view(cast(
                    Any,
                    {method.lower(): bulk_action.name for method in bulk_action.methods}
                )),
                name=f"{basename}-{url_name}",
            )
        )
    for field_subresource in field_subresources:
        action_path = f"{detail_path}{field_subresource.url_path or field_subresource.field_name}/"
        url_name = field_subresource.url_name or field_subresource.field_name
        urlpatterns.append(
            path(
                action_path,
                viewset_class.as_view(cast(
                    Any,
                    {method.lower(): field_subresource.field_name for method in field_subresource.methods}
                )),
                name=f"{basename}-{url_name}",
            )
        )
    return urlpatterns


def collection_actions_for_mode(read_only: bool) -> dict[str, str]:
    """Return the base collection action map for one generated ViewSet."""
    actions = {"get": "list"}
    if not read_only:
        actions["post"] = "create"
    return actions


def detail_actions_for_mode(read_only: bool) -> dict[str, str]:
    """Return the base detail action map for one generated ViewSet."""
    actions = {"get": "retrieve"}
    if not read_only:
        actions["put"] = "update"
        actions["patch"] = "partial_update"
        actions["delete"] = "destroy"
    return actions
