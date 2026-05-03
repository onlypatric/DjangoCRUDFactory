from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .acl import (
    ACLActionConfig,
    ACLBackend,
    ACLConfig,
    crud_acl,
    global_read_acl,
    global_read_write_acl,
    scoped_read_acl,
    scoped_read_write_acl,
)
from .actions import (
    GroupedCollectionSourceACL,
    collection_action,
    detail_action,
    grouped_collection_action,
)
from .bulk_actions import (
    BulkActionSpec,
    BulkFieldErrorDTO,
    BulkMutationResultDTO,
    BulkRowErrorDTO,
    bulk_create_action,
    bulk_delete_action,
    bulk_patch_action,
    bulk_update_action,
)
from .annotations import annotated_field, latest_related_value
from .enum_stats import enum_summary
from .factory import CRUDFactory
from .field_subresources import FieldSubresourceSpec, field_subresource
from .lifecycle import LifecycleConfig, archive_lifecycle, soft_delete_lifecycle
from ._nested_writes import NestedWriteSpec, nested_relation
from .filters import filterable
from .list_queries import (
    query_exclude,
    query_filter,
    query_list,
    query_ordering,
    query_range,
    query_search,
)
from .metadata import compose_meta
from .ordering import orderable
from .pagination import page_number_pagination
from .parent_scopes import ParentScopeSpec, parent_scope
from .query_plans import AutoQueryPlan, QueryPlan, auto_query_plan, derive_query_plan
from .related_collections import related_list
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
    "BulkActionSpec",
    "BulkFieldErrorDTO",
    "BulkMutationResultDTO",
    "BulkRowErrorDTO",
    "FieldSubresourceSpec",
    "GroupedCollectionSourceACL",
    "LifecycleConfig",
    "NestedWriteSpec",
    "AutoQueryPlan",
    "ParentScopeSpec",
    "QueryPlan",
    "avg_stat",
    "annotated_field",
    "latest_related_value",
    "bulk_create_action",
    "bulk_delete_action",
    "bulk_patch_action",
    "bulk_update_action",
    "choices",
    "collection_action",
    "compose_meta",
    "count_stat",
    "crud_acl",
    "detail_action",
    "DjangoACLBackend",
    "DjangoACLService",
    "enum_summary",
    "filterable",
    "field_subresource",
    "global_read_acl",
    "global_read_write_acl",
    "grouped_collection_action",
    "archive_lifecycle",
    "length",
    "max_stat",
    "min_stat",
    "model_field",
    "nested_relation",
    "orderable",
    "page_number_pagination",
    "parent_scope",
    "query_exclude",
    "query_filter",
    "query_list",
    "query_ordering",
    "query_range",
    "query_search",
    "auto_query_plan",
    "derive_query_plan",
    "range_",
    "regex",
    "related_list",
    "scoped_read_acl",
    "scoped_read_write_acl",
    "soft_delete_lifecycle",
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
