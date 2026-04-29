from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable, Sequence, cast

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from .acl import ACLBackend
from .config import get_crudfactory_settings
from .models import (
    AclEffect,
    AclGrant,
    AclGroupMember,
    AclPermission,
    AclResourceClosure,
    AclResourceNode,
    AclSubjectKind,
)

__all__ = [
    "ACLResourceRef",
    "DjangoACLBackend",
    "DjangoACLService",
]


@dataclass(frozen=True)
class ACLResourceRef:
    """Stable resource reference used by the Django ACL backend."""

    resource_type: str
    resource_key: str


@dataclass(frozen=True)
class GrantDecision:
    """One normalized grant candidate considered during evaluation."""

    effect: str
    depth: int
    subject_kind: str


class DjangoACLBackend(ACLBackend):
    """ACL backend adapter backed by CRUDFactory's Django ORM models."""

    def __init__(self, service: DjangoACLService | None = None) -> None:
        self.service = service or DjangoACLService()

    def has_permission(self, actor: object, permission: str) -> bool:
        if not get_crudfactory_settings().acl_enabled:
            return False
        return self.service.has_permission(actor, permission)

    def has_permission_on_resource(
        self,
        actor: object,
        permission: str,
        resource_ref: object,
    ) -> bool:
        if not get_crudfactory_settings().acl_enabled:
            return False
        return self.service.has_permission_on_resource(actor, permission, resource_ref)


class DjangoACLService:
    """Service layer implementing the ACL behavior from the design docs."""

    admin_permission_key = "app.admin.full"
    global_depth = 1_000_000

    def has_permission(self, actor: object, permission_key: str) -> bool:
        """Return whether the actor has the global permission."""
        if permission_key != self.admin_permission_key and self.has_admin_full(actor):
            return True
        user = self.resolve_active_user(actor)
        if user is None:
            return False
        permission = self.active_permission(permission_key)
        if permission is None:
            return False
        decisions = self.global_grant_decisions(user.pk, permission)
        return evaluate_grant_decisions(decisions)

    def has_permission_on_resource(
        self,
        actor: object,
        permission_key: str,
        resource_ref: object,
    ) -> bool:
        """Return whether the actor has permission on one resource node."""
        if self.has_admin_full(actor):
            return True
        user = self.resolve_active_user(actor)
        if user is None:
            return False
        permission = self.active_permission(permission_key)
        if permission is None:
            return False
        resource_node = self.resolve_resource_node(resource_ref)
        if resource_node is None:
            return False
        decisions = self.scoped_grant_decisions(user.pk, permission, resource_node.pk)
        return evaluate_grant_decisions(decisions)

    def filter_allowed_resource_node_ids(
        self,
        actor: object,
        permission_key: str,
        resource_node_ids: Iterable[int],
    ) -> list[int]:
        """Return only resource node ids the actor may access."""
        allowed_ids: list[int] = []
        for resource_node_id in resource_node_ids:
            if self.has_permission_on_resource(
                actor,
                permission_key,
                self.resource_ref_for_node_id(resource_node_id),
            ):
                allowed_ids.append(resource_node_id)
        return allowed_ids

    def filter_queryset_by_resource_node(
        self,
        queryset: models.QuerySet[Any],
        actor: object,
        permission_key: str,
        *,
        resource_node_field: str = "resource_node_id",
    ) -> models.QuerySet[Any]:
        """Filter a queryset that exposes one `resource_node_id` style field."""
        resource_node_ids = list(
            queryset.values_list(resource_node_field, flat=True).distinct()
        )
        allowed_ids = self.filter_allowed_resource_node_ids(
            actor,
            permission_key,
            [resource_node_id for resource_node_id in resource_node_ids if resource_node_id is not None],
        )
        return queryset.filter(**{f"{resource_node_field}__in": allowed_ids})

    def resolve_active_user(self, actor: object) -> models.Model | None:
        """Resolve one active Django user from an actor object or user id."""
        if hasattr(actor, "is_authenticated"):
            user = cast(models.Model, actor)
            if not bool(getattr(user, "is_authenticated", False)):
                return None
            if not bool(getattr(user, "is_active", False)):
                return None
            return user
        if not isinstance(actor, int):
            return None
        user_model = get_user_model()
        try:
            user = user_model.objects.get(pk=actor, is_active=True)
        except user_model.DoesNotExist:
            return None
        return cast(models.Model, user)

    def has_admin_full(self, actor: object) -> bool:
        """Return True when the actor has the hard-coded super permission."""
        if actor is None:
            return False
        user = self.resolve_active_user(actor)
        if user is None:
            return False
        permission = self.active_permission(self.admin_permission_key)
        if permission is None:
            return False
        decisions = self.global_grant_decisions(user.pk, permission)
        return evaluate_grant_decisions(decisions)

    def active_permission(self, permission_key: str) -> AclPermission | None:
        """Return one active permission catalog row by key."""
        try:
            return AclPermission.objects.get(permission_key=permission_key, is_active=True)
        except AclPermission.DoesNotExist:
            return None

    def resolve_resource_node(self, resource_ref: object) -> AclResourceNode | None:
        """Resolve a resource node from one accepted reference shape."""
        normalized_ref = normalize_resource_ref(resource_ref)
        if normalized_ref is None:
            return None
        try:
            return AclResourceNode.objects.get(
                resource_type=normalized_ref.resource_type,
                resource_key=normalized_ref.resource_key,
                is_active=True,
            )
        except AclResourceNode.DoesNotExist:
            return None

    def resource_ref_for_node_id(self, resource_node_id: int) -> ACLResourceRef:
        """Return an ACLResourceRef for one persisted resource node id."""
        resource_node = AclResourceNode.objects.get(pk=resource_node_id)
        return ACLResourceRef(
            resource_type=resource_node.resource_type,
            resource_key=resource_node.resource_key,
        )

    def global_grant_decisions(
        self,
        user_id: object,
        permission: AclPermission,
    ) -> list[GrantDecision]:
        """Return normalized global grant candidates for one user and permission."""
        return [
            GrantDecision(
                effect=grant.effect,
                depth=self.global_depth,
                subject_kind=grant.subject_kind,
            )
            for grant in active_global_grants_for_user(user_id, permission)
        ]

    def scoped_grant_decisions(
        self,
        user_id: object,
        permission: AclPermission,
        resource_node_id: object,
    ) -> list[GrantDecision]:
        """Return normalized scoped plus global grant candidates."""
        decisions: list[GrantDecision] = self.global_grant_decisions(user_id, permission)
        scoped_grants = active_scoped_grants_for_user(
            user_id=user_id,
            permission=permission,
            resource_node_id=resource_node_id,
        )
        decisions.extend(
            GrantDecision(
                effect=grant.effect,
                depth=depth,
                subject_kind=grant.subject_kind,
            )
            for grant, depth in scoped_grants
        )
        return decisions


def normalize_resource_ref(resource_ref: object) -> ACLResourceRef | None:
    """Normalize the supported resource-ref shapes into ACLResourceRef."""
    if isinstance(resource_ref, ACLResourceRef):
        return resource_ref
    if isinstance(resource_ref, tuple) and len(resource_ref) == 2:
        resource_type, resource_key = resource_ref
        if isinstance(resource_type, str) and isinstance(resource_key, str):
            return ACLResourceRef(resource_type=resource_type, resource_key=resource_key)
    resource_type = getattr(resource_ref, "resource_type", None)
    resource_key = getattr(resource_ref, "resource_key", None)
    if isinstance(resource_type, str) and isinstance(resource_key, str):
        return ACLResourceRef(resource_type=resource_type, resource_key=resource_key)
    return None


def active_global_grants_for_user(
    user_id: object,
    permission: AclPermission,
) -> list[AclGrant]:
    """Return active global grants directly on the user or inherited via groups."""
    return list(
        active_grants_queryset(permission)
        .filter(resource__isnull=True)
        .filter(subject_filter(user_id))
    )


def active_scoped_grants_for_user(
    *,
    user_id: object,
    permission: AclPermission,
    resource_node_id: object,
) -> list[tuple[AclGrant, int]]:
    """Return active grants inherited from the resource closure path."""
    closure_by_ancestor = {
        cast(int, closure.ancestor.pk): closure.depth
        for closure in AclResourceClosure.objects.filter(descendant_id=resource_node_id)
    }
    if not closure_by_ancestor:
        return []
    grants = list(
        active_grants_queryset(permission)
        .filter(subject_filter(user_id))
        .filter(resource_id__in=closure_by_ancestor)
        .exclude(resource__isnull=True)
    )
    return [
        (grant, closure_by_ancestor[cast(int, grant.resource.pk)])
        for grant in grants
        if grant.resource is not None
    ]


def active_grants_queryset(permission: AclPermission) -> models.QuerySet[AclGrant]:
    """Return the base queryset for active grants on one permission."""
    now = timezone.now()
    return AclGrant.objects.filter(
        permission=permission,
        enabled=True,
    ).filter(
        active_window_q(now),
    )


def active_group_ids_for_user(user_id: object) -> list[object]:
    """Return ACL group ids whose membership is currently active."""
    now = timezone.now()
    return list(
        AclGroupMember.objects.filter(user_id=user_id)
        .filter(active_window_q(now))
        .values_list("group_id", flat=True)
    )


def subject_filter(user_id: object) -> models.Q:
    """Return the queryset filter for user grants plus active group grants."""
    group_ids = active_group_ids_for_user(user_id)
    return (
        models.Q(
            subject_kind=AclSubjectKind.USER,
            subject_user_id=user_id,
        )
        | models.Q(
            subject_kind=AclSubjectKind.GROUP,
            subject_group_id__in=group_ids,
        )
    )


def active_window_q(now: dt.datetime) -> models.Q:
    """Return the standard time-window filter shared by grants and memberships."""
    return (
        (models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
        & (models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))
    )


def evaluate_grant_decisions(decisions: Sequence[GrantDecision]) -> bool:
    """Evaluate grants using the precedence rules from the ACL design docs."""
    if not decisions:
        return False
    winning_decision = sorted(decisions, key=grant_sort_key)[0]
    return winning_decision.effect == AclEffect.ALLOW


def grant_sort_key(decision: GrantDecision) -> tuple[int, int]:
    """Sort first by proximity, then by user/group and deny/allow precedence."""
    return (decision.depth, subject_effect_rank(decision.subject_kind, decision.effect))


def subject_effect_rank(subject_kind: str, effect: str) -> int:
    """Return the deterministic tie-break rank defined by the ACL docs."""
    ranks = {
        (AclSubjectKind.USER, AclEffect.DENY): 0,
        (AclSubjectKind.USER, AclEffect.ALLOW): 1,
        (AclSubjectKind.GROUP, AclEffect.DENY): 2,
        (AclSubjectKind.GROUP, AclEffect.ALLOW): 3,
    }
    return ranks[(AclSubjectKind(subject_kind), AclEffect(effect))]
