from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .acl import ACLActionConfig, ACLBackend, ACLConfig, crud_acl
from .actions import (
    GroupedCollectionSourceACL,
    collection_action,
    detail_action,
    grouped_collection_action,
)
from .factory import CRUDFactory
from .filters import filterable
from .ordering import orderable
from .pagination import page_number_pagination
from ._simple_writes import model_field
from .source_queries import source_filterable, source_orderable
from .stats import avg_stat, count_stat, max_stat, min_stat, sum_stat
from .validators import choices, length, range_, regex

if TYPE_CHECKING:
    from .acl_bootstrap import (
        ACLBootstrapper,
        ACLGroupSeed,
        ACLPermissionSeed,
        ACLResourceSeed,
    )
    from .django_acl import ACLResourceRef, DjangoACLBackend, DjangoACLService

__all__ = [
    "CRUDFactory",
    "ACLActionConfig",
    "ACLBackend",
    "ACLBootstrapper",
    "ACLConfig",
    "ACLGroupSeed",
    "ACLPermissionSeed",
    "ACLResourceRef",
    "ACLResourceSeed",
    "GroupedCollectionSourceACL",
    "avg_stat",
    "choices",
    "collection_action",
    "count_stat",
    "crud_acl",
    "detail_action",
    "DjangoACLBackend",
    "DjangoACLService",
    "filterable",
    "grouped_collection_action",
    "length",
    "max_stat",
    "min_stat",
    "model_field",
    "orderable",
    "page_number_pagination",
    "range_",
    "regex",
    "source_filterable",
    "source_orderable",
    "sum_stat",
]


def __getattr__(name: str) -> Any:
    """Import Django-backed ACL helpers lazily so app loading stays safe."""
    if name in {"ACLResourceRef", "DjangoACLBackend", "DjangoACLService"}:
        module = import_module(".django_acl", __name__)
        return getattr(module, name)
    if name in {
        "ACLBootstrapper",
        "ACLGroupSeed",
        "ACLPermissionSeed",
        "ACLResourceSeed",
    }:
        module = import_module(".acl_bootstrap", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
