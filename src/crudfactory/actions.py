from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Sequence, TypeVar, cast

from django.db import models

from .acl import ACLActionConfig, ACLMode, ListFilterMode, QuerysetFilter
from .types import M

ActionInputDTO = TypeVar("ActionInputDTO")
ActionResponseDTO = TypeVar("ActionResponseDTO")
QueryDTO = TypeVar("QueryDTO")

DetailActionHandler = Callable[[M, ActionInputDTO], ActionResponseDTO]
CollectionActionHandler = Callable[
    [models.QuerySet[M], ActionInputDTO],
    ActionResponseDTO,
]
GroupedCollectionActionHandler = Callable[
    [models.QuerySet[M] | Sequence[M], QueryDTO],
    ActionResponseDTO,
]

__all__ = [
    "CollectionActionHandler",
    "CustomActionSpec",
    "DetailActionHandler",
    "GroupedCollectionActionHandler",
    "GroupedCollectionActionSpec",
    "GroupedCollectionSourceACL",
    "collection_action",
    "detail_action",
    "grouped_collection_action",
]


@dataclass(frozen=True)
class CustomActionSpec(Generic[M]):
    """One typed extra action exposed by a generated CRUDFactory ViewSet.

    `detail=True` creates routes such as `POST /items/{id}/activate/` and calls
    the handler with `(instance, dto)`.

    `detail=False` creates routes such as `POST /items/bulk-import/` and calls
    the handler with `(queryset, dto)`.
    """

    name: str
    detail: bool
    methods: tuple[str, ...]
    input_dataclass: type[object]
    response_dataclass: type[object]
    handler: Callable[..., object]
    url_path: str | None
    url_name: str | None
    acl: ACLActionConfig | None
    acl_resource_ref_resolver: Callable[..., object] | None


@dataclass(frozen=True)
class GroupedCollectionSourceACL(Generic[M]):
    """Source-row ACL filtering rules for one grouped collection action."""

    permission: str
    mode: ACLMode = "scoped"
    unauthorized_as_404: bool = False
    list_filter_mode: ListFilterMode = "filter"
    resource_ref_from_instance: Callable[[M], object] | None = None
    queryset_filter: QuerysetFilter[M] | None = None


@dataclass(frozen=True)
class GroupedCollectionActionSpec(Generic[M]):
    """One read-only grouped collection endpoint over the factory queryset."""

    name: str
    methods: tuple[str, ...]
    query_dataclass: type[object]
    response_dataclass: type[object]
    handler: Callable[..., object]
    url_path: str | None
    url_name: str | None
    source_acl: GroupedCollectionSourceACL[M] | None


def detail_action(
    *,
    name: str,
    input_dataclass: type[ActionInputDTO],
    response_dataclass: type[ActionResponseDTO],
    handler: DetailActionHandler[M, ActionInputDTO, ActionResponseDTO],
    methods: tuple[str, ...] = ("post",),
    url_path: str | None = None,
    url_name: str | None = None,
    acl: ACLActionConfig | None = None,
    acl_resource_ref_resolver: Callable[[M, ActionInputDTO], object] | None = None,
) -> CustomActionSpec[M]:
    """Return a typed detail action spec for one model instance."""
    return CustomActionSpec(
        name=name,
        detail=True,
        methods=normalize_methods(methods),
        input_dataclass=cast(type[object], input_dataclass),
        response_dataclass=cast(type[object], response_dataclass),
        handler=cast(Callable[..., object], handler),
        url_path=url_path,
        url_name=url_name,
        acl=acl,
        acl_resource_ref_resolver=cast(
            Callable[..., object] | None,
            acl_resource_ref_resolver,
        ),
    )


def collection_action(
    *,
    name: str,
    input_dataclass: type[ActionInputDTO],
    response_dataclass: type[ActionResponseDTO],
    handler: CollectionActionHandler[M, ActionInputDTO, ActionResponseDTO],
    methods: tuple[str, ...] = ("post",),
    url_path: str | None = None,
    url_name: str | None = None,
    acl: ACLActionConfig | None = None,
    acl_resource_ref_resolver: Callable[[ActionInputDTO], object] | None = None,
) -> CustomActionSpec[M]:
    """Return a typed collection action spec for a generated ViewSet."""
    return CustomActionSpec(
        name=name,
        detail=False,
        methods=normalize_methods(methods),
        input_dataclass=cast(type[object], input_dataclass),
        response_dataclass=cast(type[object], response_dataclass),
        handler=cast(Callable[..., object], handler),
        url_path=url_path,
        url_name=url_name,
        acl=acl,
        acl_resource_ref_resolver=cast(
            Callable[..., object] | None,
            acl_resource_ref_resolver,
        ),
    )


def grouped_collection_action(
    *,
    name: str,
    query_dataclass: type[QueryDTO],
    response_dataclass: type[ActionResponseDTO],
    handler: GroupedCollectionActionHandler[M, QueryDTO, ActionResponseDTO],
    methods: tuple[str, ...] = ("get",),
    url_path: str | None = None,
    url_name: str | None = None,
    source_acl: GroupedCollectionSourceACL[M] | None = None,
) -> GroupedCollectionActionSpec[M]:
    """Return a grouped read-only collection action spec.

    Grouped collection actions are intended for GET endpoints that:

    - start from the factory queryset
    - optionally filter/order that queryset using query params
    - optionally apply source-row ACL filtering
    - reduce many model rows into one grouped response DTO
    """
    return GroupedCollectionActionSpec(
        name=name,
        methods=normalize_methods(methods),
        query_dataclass=cast(type[object], query_dataclass),
        response_dataclass=cast(type[object], response_dataclass),
        handler=cast(Callable[..., object], handler),
        url_path=url_path,
        url_name=url_name,
        source_acl=source_acl,
    )


def normalize_methods(methods: tuple[str, ...]) -> tuple[str, ...]:
    """Return lower-case HTTP methods after validating action configuration."""
    normalized_methods = tuple(method.lower() for method in methods)
    if not normalized_methods:
        msg = "Custom actions must expose at least one HTTP method."
        raise ValueError(msg)
    return normalized_methods
