from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Literal, Protocol, Sequence

from django.db import models
from rest_framework.request import Request

from .types import CreateDTO, M, PatchDTO, UpdateDTO

ACLMode = Literal["global", "scoped", "disabled"]
ListFilterMode = Literal["filter", "forbid"]

CreateRefResolver = Callable[[CreateDTO], object]
UpdateRefResolver = Callable[[M, UpdateDTO], object]
PatchRefResolver = Callable[[M, PatchDTO], object]
InstanceRefResolver = Callable[[M], object]
ActorResolver = Callable[[Request], object]
CollectionActionRefResolver = Callable[[object], object]
DetailActionRefResolver = Callable[[M, object], object]
QuerysetFilter = Callable[
    [models.QuerySet[M], object, str, InstanceRefResolver[M] | None],
    models.QuerySet[M] | Sequence[M],
]

__all__ = [
    "ACLActionConfig",
    "ACLBackend",
    "ACLConfig",
    "ACLMode",
    "ListFilterMode",
    "crud_acl",
    "global_read_acl",
    "global_read_write_acl",
    "scoped_read_acl",
    "scoped_read_write_acl",
]


class ACLBackend(Protocol):
    """Small protocol CRUDFactory uses to ask ACL questions.

    The backend may wrap a fully fledged ACL engine, a service layer, or a
    simpler adapter around another authorization system.  CRUDFactory only
    needs one global permission check and one resource-scoped permission check.
    """

    def has_permission(self, actor: object, permission: str) -> bool:
        """Return whether the actor has a global permission."""
        ...

    def has_permission_on_resource(
        self,
        actor: object,
        permission: str,
        resource_ref: object,
    ) -> bool:
        """Return whether the actor has the permission on one resource."""
        ...


def default_actor_resolver(request: Request) -> object:
    """Return the default ACL actor derived from DRF's request."""
    return request.user


@dataclass(frozen=True)
class ACLActionConfig:
    """ACL behavior for one generated CRUD action."""

    permission: str
    mode: ACLMode = "scoped"
    unauthorized_as_404: bool = True


@dataclass(frozen=True)
class ACLConfig(Generic[M, CreateDTO, UpdateDTO, PatchDTO]):
    """Factory-level ACL integration configuration.

    The config is intentionally small and explicit.  CRUDFactory stays generic
    by requiring callers to describe how one endpoint maps to:

    - the permission key used for each action
    - the target resource reference for scoped checks
    - the actor extracted from the incoming request
    - optional queryset filtering for efficient scoped lists
    """

    backend: ACLBackend
    list_action: ACLActionConfig | None = None
    retrieve_action: ACLActionConfig | None = None
    create_action: ACLActionConfig | None = None
    update_action: ACLActionConfig | None = None
    partial_update_action: ACLActionConfig | None = None
    destroy_action: ACLActionConfig | None = None
    list_filter_mode: ListFilterMode = "filter"
    actor_resolver: ActorResolver = default_actor_resolver
    resource_ref_from_instance: InstanceRefResolver[M] | None = None
    resource_ref_from_create_input: CreateRefResolver[CreateDTO] | None = None
    resource_ref_from_update_input: UpdateRefResolver[M, UpdateDTO] | None = None
    resource_ref_from_patch_input: PatchRefResolver[M, PatchDTO] | None = None
    queryset_filter: QuerysetFilter[M] | None = None


def crud_acl(
    *,
    backend: ACLBackend,
    permission_prefix: str,
    mode: ACLMode = "scoped",
    unauthorized_as_404: bool = True,
    list_filter_mode: ListFilterMode = "filter",
    actor_resolver: ActorResolver = default_actor_resolver,
    resource_ref_from_instance: InstanceRefResolver[M] | None = None,
    resource_ref_from_create_input: CreateRefResolver[CreateDTO] | None = None,
    resource_ref_from_update_input: UpdateRefResolver[M, UpdateDTO] | None = None,
    resource_ref_from_patch_input: PatchRefResolver[M, PatchDTO] | None = None,
    queryset_filter: QuerysetFilter[M] | None = None,
) -> ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO]:
    """Return an ACLConfig using the default CRUD permission suffix mapping.

    The default convention mirrors the policy proposed in the ACL design notes:

    - `list` -> `{permission_prefix}.read`
    - `retrieve` -> `{permission_prefix}.read`
    - `create` -> `{permission_prefix}.create`
    - `update` -> `{permission_prefix}.update`
    - `partial_update` -> `{permission_prefix}.update`
    - `destroy` -> `{permission_prefix}.delete`
    """
    return ACLConfig(
        backend=backend,
        list_action=ACLActionConfig(
            permission=permission_key(permission_prefix, "read"),
            mode=mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        retrieve_action=ACLActionConfig(
            permission=permission_key(permission_prefix, "read"),
            mode=mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        create_action=ACLActionConfig(
            permission=permission_key(permission_prefix, "create"),
            mode=mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        update_action=ACLActionConfig(
            permission=permission_key(permission_prefix, "update"),
            mode=mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        partial_update_action=ACLActionConfig(
            permission=permission_key(permission_prefix, "update"),
            mode=mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        destroy_action=ACLActionConfig(
            permission=permission_key(permission_prefix, "delete"),
            mode=mode,
            unauthorized_as_404=unauthorized_as_404,
        ),
        list_filter_mode=list_filter_mode,
        actor_resolver=actor_resolver,
        resource_ref_from_instance=resource_ref_from_instance,
        resource_ref_from_create_input=resource_ref_from_create_input,
        resource_ref_from_update_input=resource_ref_from_update_input,
        resource_ref_from_patch_input=resource_ref_from_patch_input,
        queryset_filter=queryset_filter,
    )


def scoped_read_acl(
    *,
    backend: ACLBackend,
    permission: str,
    unauthorized_as_404: bool = True,
    list_filter_mode: ListFilterMode = "filter",
    actor_resolver: ActorResolver = default_actor_resolver,
    resource_ref_from_instance: InstanceRefResolver[M],
    queryset_filter: QuerysetFilter[M] | None = None,
) -> ACLConfig[M, object, object, object]:
    """Return a scoped read-only ACLConfig for common list/retrieve endpoints."""
    read_action = ACLActionConfig(
        permission=permission,
        mode="scoped",
        unauthorized_as_404=unauthorized_as_404,
    )
    return ACLConfig(
        backend=backend,
        list_action=read_action,
        retrieve_action=read_action,
        list_filter_mode=list_filter_mode,
        actor_resolver=actor_resolver,
        resource_ref_from_instance=resource_ref_from_instance,
        queryset_filter=queryset_filter,
    )


def scoped_read_write_acl(
    *,
    backend: ACLBackend,
    read_permission: str,
    create_permission: str,
    update_permission: str,
    delete_permission: str,
    unauthorized_as_404: bool = True,
    list_filter_mode: ListFilterMode = "filter",
    actor_resolver: ActorResolver = default_actor_resolver,
    resource_ref_from_instance: InstanceRefResolver[M],
    resource_ref_from_create_input: CreateRefResolver[CreateDTO] | None = None,
    resource_ref_from_update_input: UpdateRefResolver[M, UpdateDTO] | None = None,
    resource_ref_from_patch_input: PatchRefResolver[M, PatchDTO] | None = None,
    queryset_filter: QuerysetFilter[M] | None = None,
) -> ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO]:
    """Return a scoped full-CRUD ACLConfig with explicit per-action permissions."""
    return ACLConfig(
        backend=backend,
        list_action=ACLActionConfig(
            permission=read_permission,
            mode="scoped",
            unauthorized_as_404=unauthorized_as_404,
        ),
        retrieve_action=ACLActionConfig(
            permission=read_permission,
            mode="scoped",
            unauthorized_as_404=unauthorized_as_404,
        ),
        create_action=ACLActionConfig(
            permission=create_permission,
            mode="scoped",
            unauthorized_as_404=unauthorized_as_404,
        ),
        update_action=ACLActionConfig(
            permission=update_permission,
            mode="scoped",
            unauthorized_as_404=unauthorized_as_404,
        ),
        partial_update_action=ACLActionConfig(
            permission=update_permission,
            mode="scoped",
            unauthorized_as_404=unauthorized_as_404,
        ),
        destroy_action=ACLActionConfig(
            permission=delete_permission,
            mode="scoped",
            unauthorized_as_404=unauthorized_as_404,
        ),
        list_filter_mode=list_filter_mode,
        actor_resolver=actor_resolver,
        resource_ref_from_instance=resource_ref_from_instance,
        resource_ref_from_create_input=resource_ref_from_create_input,
        resource_ref_from_update_input=resource_ref_from_update_input,
        resource_ref_from_patch_input=resource_ref_from_patch_input,
        queryset_filter=queryset_filter,
    )


def global_read_acl(
    *,
    backend: ACLBackend,
    permission: str,
    unauthorized_as_404: bool = True,
    list_filter_mode: ListFilterMode = "filter",
    actor_resolver: ActorResolver = default_actor_resolver,
) -> ACLConfig[models.Model, object, object, object]:
    """Return a global read-only ACLConfig for common list/retrieve endpoints."""
    read_action = ACLActionConfig(
        permission=permission,
        mode="global",
        unauthorized_as_404=unauthorized_as_404,
    )
    return ACLConfig(
        backend=backend,
        list_action=read_action,
        retrieve_action=read_action,
        list_filter_mode=list_filter_mode,
        actor_resolver=actor_resolver,
    )


def global_read_write_acl(
    *,
    backend: ACLBackend,
    read_permission: str,
    create_permission: str,
    update_permission: str,
    delete_permission: str,
    unauthorized_as_404: bool = True,
    list_filter_mode: ListFilterMode = "filter",
    actor_resolver: ActorResolver = default_actor_resolver,
) -> ACLConfig[models.Model, object, object, object]:
    """Return a global full-CRUD ACLConfig with explicit per-action permissions."""
    return ACLConfig(
        backend=backend,
        list_action=ACLActionConfig(
            permission=read_permission,
            mode="global",
            unauthorized_as_404=unauthorized_as_404,
        ),
        retrieve_action=ACLActionConfig(
            permission=read_permission,
            mode="global",
            unauthorized_as_404=unauthorized_as_404,
        ),
        create_action=ACLActionConfig(
            permission=create_permission,
            mode="global",
            unauthorized_as_404=unauthorized_as_404,
        ),
        update_action=ACLActionConfig(
            permission=update_permission,
            mode="global",
            unauthorized_as_404=unauthorized_as_404,
        ),
        partial_update_action=ACLActionConfig(
            permission=update_permission,
            mode="global",
            unauthorized_as_404=unauthorized_as_404,
        ),
        destroy_action=ACLActionConfig(
            permission=delete_permission,
            mode="global",
            unauthorized_as_404=unauthorized_as_404,
        ),
        list_filter_mode=list_filter_mode,
        actor_resolver=actor_resolver,
    )


def permission_key(permission_prefix: str, action_name: str) -> str:
    """Return a permission key using the default CRUD suffix convention."""
    return f"{permission_prefix}.{action_name}"
