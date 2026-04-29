from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, cast

from django.db import models

from .acl import ACLActionConfig
from .types import M

ActionInputDTO = TypeVar("ActionInputDTO")
ActionResponseDTO = TypeVar("ActionResponseDTO")

DetailActionHandler = Callable[[M, ActionInputDTO], ActionResponseDTO]
CollectionActionHandler = Callable[
    [models.QuerySet[M], ActionInputDTO],
    ActionResponseDTO,
]

__all__ = [
    "CollectionActionHandler",
    "CustomActionSpec",
    "DetailActionHandler",
    "collection_action",
    "detail_action",
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


def normalize_methods(methods: tuple[str, ...]) -> tuple[str, ...]:
    """Return lower-case HTTP methods after validating action configuration."""
    normalized_methods = tuple(method.lower() for method in methods)
    if not normalized_methods:
        msg = "Custom actions must expose at least one HTTP method."
        raise ValueError(msg)
    return normalized_methods
