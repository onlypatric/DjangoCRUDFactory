from __future__ import annotations

from typing import Callable, Sequence, cast

from django.db import models
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request

from .acl import ACLActionConfig, ACLBackend, ACLConfig
from .actions import CustomActionSpec, GroupedCollectionSourceACL
from .types import CreateDTO, M, PatchDTO, UpdateDTO

__all__: list[str] = []


def filter_collection_for_acl(
    *,
    queryset: models.QuerySet[M],
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    action_config: ACLActionConfig | None,
) -> models.QuerySet[M] | Sequence[M]:
    """Return a list/queryset filtered by ACL for a list-style action."""
    if acl is None or action_is_disabled(action_config):
        return queryset
    checked_action = require_action_config("list ACL", action_config)
    actor = acl.actor_resolver(request)
    if checked_action.mode == "global":
        enforce_global_permission(
            backend=acl.backend,
            actor=actor,
            action_config=checked_action,
        )
        return queryset
    if acl.queryset_filter is not None:
        return cast(
            models.QuerySet[M] | Sequence[M],
            acl.queryset_filter(
                queryset,
                actor,
                checked_action.permission,
                acl.resource_ref_from_instance,
            ),
        )
    if acl.resource_ref_from_instance is not None:
        return [
            instance
            for instance in queryset
            if acl.backend.has_permission_on_resource(
                actor,
                checked_action.permission,
                acl.resource_ref_from_instance(instance),
            )
        ]
    if acl.list_filter_mode == "forbid":
        raise PermissionDenied("ACL list filtering requires a resource resolver.")
    msg = (
        "Scoped list ACL requires resource_ref_from_instance or queryset_filter."
    )
    raise TypeError(msg)


def filter_grouped_collection_for_acl(
    *,
    queryset: models.QuerySet[M],
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    source_acl: GroupedCollectionSourceACL[M] | None,
) -> models.QuerySet[M] | Sequence[M]:
    """Return grouped-action source rows filtered by per-row scoped ACL."""
    if source_acl is None or source_acl.mode == "disabled":
        return queryset
    if acl is None:
        msg = "Grouped source ACL requires a factory-level acl configuration."
        raise TypeError(msg)
    actor = acl.actor_resolver(request)
    if source_acl.mode == "global":
        if not acl.backend.has_permission(actor, source_acl.permission):
            raise PermissionDenied("You do not have permission to perform this action.")
        return queryset
    if source_acl.queryset_filter is not None:
        return cast(
            models.QuerySet[M] | Sequence[M],
            source_acl.queryset_filter(
                queryset,
                actor,
                source_acl.permission,
                source_acl.resource_ref_from_instance,
            ),
        )
    if source_acl.resource_ref_from_instance is not None:
        return [
            instance
            for instance in queryset
            if acl.backend.has_permission_on_resource(
                actor,
                source_acl.permission,
                source_acl.resource_ref_from_instance(instance),
            )
        ]
    if source_acl.list_filter_mode == "forbid":
        raise PermissionDenied("Grouped source ACL requires a resource resolver.")
    msg = (
        "Scoped grouped source ACL requires resource_ref_from_instance "
        "or queryset_filter."
    )
    raise TypeError(msg)


def enforce_instance_acl(
    *,
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    action_config: ACLActionConfig | None,
    instance: M,
    resolver: Callable[[M], object] | None,
) -> None:
    """Raise when the current actor cannot access one model instance."""
    if acl is None or action_is_disabled(action_config):
        return
    checked_action = require_action_config("instance ACL", action_config)
    actor = acl.actor_resolver(request)
    if checked_action.mode == "global":
        enforce_global_permission(
            backend=acl.backend,
            actor=actor,
            action_config=checked_action,
        )
        return
    checked_resolver = require_resolver("resource_ref_from_instance", resolver)
    allowed = acl.backend.has_permission_on_resource(
        actor,
        checked_action.permission,
        checked_resolver(instance),
    )
    if not allowed:
        raise_unauthorized_for_action(checked_action)


def enforce_create_acl(
    *,
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    action_config: ACLActionConfig | None,
    dto: CreateDTO,
) -> None:
    """Raise when the current actor cannot create inside the target scope."""
    if acl is None or action_is_disabled(action_config):
        return
    checked_action = require_action_config("create ACL", action_config)
    actor = acl.actor_resolver(request)
    if checked_action.mode == "global":
        enforce_global_permission(
            backend=acl.backend,
            actor=actor,
            action_config=checked_action,
        )
        return
    resolver = require_resolver(
        "resource_ref_from_create_input",
        acl.resource_ref_from_create_input,
    )
    allowed = acl.backend.has_permission_on_resource(
        actor,
        checked_action.permission,
        resolver(dto),
    )
    if not allowed:
        raise_unauthorized_for_action(checked_action)


def enforce_target_update_acl(
    *,
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    action_config: ACLActionConfig | None,
    instance: M,
    dto: UpdateDTO,
    resolver: Callable[[M, UpdateDTO], object] | None,
) -> None:
    """Raise when an update would move an object into a forbidden scope."""
    if acl is None or action_is_disabled(action_config) or resolver is None:
        return
    checked_action = require_action_config("update ACL", action_config)
    if checked_action.mode == "disabled":
        return
    actor = acl.actor_resolver(request)
    if checked_action.mode == "global":
        enforce_global_permission(
            backend=acl.backend,
            actor=actor,
            action_config=checked_action,
        )
        return
    allowed = acl.backend.has_permission_on_resource(
        actor,
        checked_action.permission,
        resolver(instance, dto),
    )
    if not allowed:
        raise_unauthorized_for_action(checked_action)


def enforce_target_patch_acl(
    *,
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    action_config: ACLActionConfig | None,
    instance: M,
    dto: PatchDTO,
    resolver: Callable[[M, PatchDTO], object] | None,
) -> None:
    """Raise when a patch would move an object into a forbidden scope."""
    if acl is None or action_is_disabled(action_config) or resolver is None:
        return
    checked_action = require_action_config("patch ACL", action_config)
    actor = acl.actor_resolver(request)
    if checked_action.mode == "global":
        enforce_global_permission(
            backend=acl.backend,
            actor=actor,
            action_config=checked_action,
        )
        return
    allowed = acl.backend.has_permission_on_resource(
        actor,
        checked_action.permission,
        resolver(instance, dto),
    )
    if not allowed:
        raise_unauthorized_for_action(checked_action)


def enforce_custom_action_acl(
    *,
    request: Request,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    custom_action: CustomActionSpec[M],
    instance: M | None,
    dto: object,
) -> None:
    """Raise when a typed custom action is not authorized."""
    action_acl = custom_action.acl
    if acl is None or action_is_disabled(action_acl):
        return
    checked_action = require_action_config(
        f"custom action {custom_action.name} ACL",
        action_acl,
    )
    actor = acl.actor_resolver(request)
    if checked_action.mode == "global":
        enforce_global_permission(
            backend=acl.backend,
            actor=actor,
            action_config=checked_action,
        )
        return
    resource_ref = custom_action_resource_ref(
        acl=acl,
        custom_action=custom_action,
        instance=instance,
        dto=dto,
    )
    allowed = acl.backend.has_permission_on_resource(
        actor,
        checked_action.permission,
        resource_ref,
    )
    if not allowed:
        raise_unauthorized_for_action(checked_action)


def custom_action_resource_ref(
    *,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO],
    custom_action: CustomActionSpec[M],
    instance: M | None,
    dto: object,
) -> object:
    """Return the resource reference used by a custom action ACL check."""
    custom_resolver = custom_action.acl_resource_ref_resolver
    if custom_action.detail:
        checked_instance = require_instance_for_detail_action(instance, custom_action.name)
        if custom_resolver is not None:
            return custom_resolver(checked_instance, dto)
        resolver = require_resolver(
            "resource_ref_from_instance",
            acl.resource_ref_from_instance,
        )
        return resolver(checked_instance)
    if custom_resolver is None:
        msg = (
            f"Collection custom action {custom_action.name!r} requires "
            "acl_resource_ref_resolver for scoped ACL."
        )
        raise TypeError(msg)
    return custom_resolver(dto)


def require_instance_for_detail_action(instance: M | None, action_name: str) -> M:
    """Return a detail action instance or fail clearly for bad configuration."""
    if instance is None:
        msg = f"Detail custom action {action_name!r} requires an instance."
        raise TypeError(msg)
    return instance


def action_is_disabled(action_config: ACLActionConfig | None) -> bool:
    """Return True when ACL is absent or explicitly disabled for an action."""
    return action_config is None or action_config.mode == "disabled"


def require_action_config(name: str, action_config: ACLActionConfig | None) -> ACLActionConfig:
    """Return one action config or fail clearly for bad internal usage."""
    if action_config is None:
        msg = f"{name} is required."
        raise TypeError(msg)
    return action_config


def require_resolver(name: str, resolver: Callable[..., object] | None) -> Callable[..., object]:
    """Return one configured resolver or raise a clear configuration error."""
    if resolver is None:
        msg = f"Scoped ACL requires {name}."
        raise TypeError(msg)
    return resolver


def enforce_global_permission(
    *,
    backend: ACLBackend,
    actor: object,
    action_config: ACLActionConfig,
) -> None:
    """Raise when a global permission check fails."""
    allowed = backend.has_permission(actor, action_config.permission)
    if not allowed:
        raise_unauthorized_for_action(action_config)


def raise_unauthorized_for_action(action_config: ACLActionConfig) -> None:
    """Raise the configured object-level error for one ACL denial."""
    if action_config.unauthorized_as_404:
        raise NotFound()
    raise PermissionDenied()
