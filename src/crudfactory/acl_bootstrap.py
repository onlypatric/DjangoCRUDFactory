from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence, cast

from django.contrib.auth import get_user_model
from django.db import transaction

from .django_acl import ACLResourceRef
from .models import (
    AclEffect,
    AclGrant,
    AclGroup,
    AclGroupMember,
    AclPermission,
    AclResourceClosure,
    AclResourceNode,
    AclSubjectKind,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

__all__ = [
    "ACLBootstrapper",
    "ACLGroupSeed",
    "ACLPermissionSeed",
    "ACLResourceSeed",
    "load_bootstrap_object",
]


@dataclass(frozen=True)
class ACLPermissionSeed:
    """One permission-catalog row that should exist after bootstrap."""

    permission_key: str
    domain: str
    action: str
    resource_type: str = ""
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class ACLGroupSeed:
    """One ACL group row that should exist after bootstrap."""

    code: str
    name: str
    description: str | None = None
    is_system: bool = False


@dataclass(frozen=True)
class ACLResourceSeed:
    """One resource node plus its optional parent reference."""

    resource_type: str
    resource_key: str
    display_name: str | None = None
    parent_ref: ACLResourceRef | tuple[str, str] | None = None
    metadata: Mapping[str, object] | None = None
    is_active: bool = True


class ACLBootstrapper:
    """Readable helper object used by management commands and project seed files."""

    def __init__(self) -> None:
        self.created_permissions = 0
        self.created_groups = 0
        self.created_resources = 0
        self.created_memberships = 0
        self.created_grants = 0

    @transaction.atomic
    def ensure_permissions(
        self,
        permission_seeds: Iterable[ACLPermissionSeed],
    ) -> list[AclPermission]:
        """Create or update the permission catalog rows from seed definitions."""
        permissions: list[AclPermission] = []
        for seed in permission_seeds:
            permission, created = AclPermission.objects.update_or_create(
                permission_key=seed.permission_key,
                defaults={
                    "domain": seed.domain,
                    "action": seed.action,
                    "resource_type": seed.resource_type,
                    "description": seed.description,
                    "is_active": seed.is_active,
                },
            )
            if created:
                self.created_permissions += 1
            permissions.append(permission)
        return permissions

    @transaction.atomic
    def ensure_groups(self, group_seeds: Iterable[ACLGroupSeed]) -> list[AclGroup]:
        """Create or update ACL groups from seed definitions."""
        groups: list[AclGroup] = []
        for seed in group_seeds:
            group, created = AclGroup.objects.update_or_create(
                code=seed.code,
                defaults={
                    "name": seed.name,
                    "description": seed.description,
                    "is_system": seed.is_system,
                },
            )
            if created:
                self.created_groups += 1
            groups.append(group)
        return groups

    @transaction.atomic
    def ensure_resources(
        self,
        resource_seeds: Sequence[ACLResourceSeed],
    ) -> list[AclResourceNode]:
        """Create or update resource nodes, then rebuild the closure table once."""
        nodes: list[AclResourceNode] = []
        for seed in resource_seeds:
            parent = self.resolve_resource_ref(seed.parent_ref)
            node, created = AclResourceNode.objects.update_or_create(
                resource_type=seed.resource_type,
                resource_key=seed.resource_key,
                defaults={
                    "display_name": seed.display_name,
                    "parent": parent,
                    "metadata": dict(seed.metadata or {}),
                    "is_active": seed.is_active,
                },
            )
            if created:
                self.created_resources += 1
            nodes.append(node)
        self.rebuild_resource_closure()
        return nodes

    @transaction.atomic
    def ensure_group_membership(
        self,
        *,
        group_code: str,
        user_identifier: str,
        starts_at: dt.datetime | None = None,
        expires_at: dt.datetime | None = None,
    ) -> AclGroupMember:
        """Ensure one user is a member of one ACL group."""
        user = self.resolve_user(user_identifier)
        group = AclGroup.objects.get(code=group_code)
        membership, created = AclGroupMember.objects.update_or_create(
            group=group,
            user=user,
            defaults={
                "starts_at": starts_at,
                "expires_at": expires_at,
            },
        )
        if created:
            self.created_memberships += 1
        return membership

    @transaction.atomic
    def ensure_user_grant(
        self,
        *,
        user_identifier: str,
        permission_key: str,
        effect: str = AclEffect.ALLOW,
        resource_ref: ACLResourceRef | tuple[str, str] | None = None,
        enabled: bool = True,
        starts_at: dt.datetime | None = None,
        expires_at: dt.datetime | None = None,
        note: str | None = None,
    ) -> AclGrant:
        """Ensure one direct user grant exists."""
        user = self.resolve_user(user_identifier)
        return self.ensure_grant(
            subject_kind=AclSubjectKind.USER,
            subject_user=user,
            subject_group=None,
            permission_key=permission_key,
            effect=effect,
            resource_ref=resource_ref,
            enabled=enabled,
            starts_at=starts_at,
            expires_at=expires_at,
            note=note,
        )

    @transaction.atomic
    def ensure_group_grant(
        self,
        *,
        group_code: str,
        permission_key: str,
        effect: str = AclEffect.ALLOW,
        resource_ref: ACLResourceRef | tuple[str, str] | None = None,
        enabled: bool = True,
        starts_at: dt.datetime | None = None,
        expires_at: dt.datetime | None = None,
        note: str | None = None,
    ) -> AclGrant:
        """Ensure one group grant exists."""
        group = AclGroup.objects.get(code=group_code)
        return self.ensure_grant(
            subject_kind=AclSubjectKind.GROUP,
            subject_user=None,
            subject_group=group,
            permission_key=permission_key,
            effect=effect,
            resource_ref=resource_ref,
            enabled=enabled,
            starts_at=starts_at,
            expires_at=expires_at,
            note=note,
        )

    def ensure_grant(
        self,
        *,
        subject_kind: str,
        subject_user: AbstractBaseUser | None,
        subject_group: AclGroup | None,
        permission_key: str,
        effect: str,
        resource_ref: ACLResourceRef | tuple[str, str] | None,
        enabled: bool,
        starts_at: dt.datetime | None,
        expires_at: dt.datetime | None,
        note: str | None,
    ) -> AclGrant:
        """Create or update one normalized ACL grant row."""
        permission = AclPermission.objects.get(permission_key=permission_key)
        resource = self.resolve_resource_ref(resource_ref)
        grant, created = AclGrant.objects.update_or_create(
            subject_kind=subject_kind,
            subject_user=subject_user,
            subject_group=subject_group,
            permission=permission,
            resource=resource,
            effect=effect,
            defaults={
                "enabled": enabled,
                "starts_at": starts_at,
                "expires_at": expires_at,
                "note": note,
            },
        )
        if created:
            self.created_grants += 1
        return grant

    def rebuild_resource_closure(self) -> None:
        """Recompute the closure table from the current parent pointers."""
        AclResourceClosure.objects.all().delete()
        closure_rows: list[AclResourceClosure] = []
        for node in AclResourceNode.objects.select_related("parent").order_by("id"):
            ancestors = list(self.ancestor_chain(node))
            for depth, ancestor in enumerate(ancestors):
                closure_rows.append(
                    AclResourceClosure(
                        ancestor=ancestor,
                        descendant=node,
                        depth=depth,
                    )
                )
        AclResourceClosure.objects.bulk_create(closure_rows)

    def ancestor_chain(self, node: AclResourceNode) -> Iterable[AclResourceNode]:
        """Yield the node first, then every ancestor until the root."""
        seen_node_ids: set[int] = set()
        current: AclResourceNode | None = node
        while current is not None:
            if current.pk in seen_node_ids:
                msg = (
                    "ACL resource tree contains a parent cycle involving "
                    f"{current.resource_type}:{current.resource_key}."
                )
                raise ValueError(msg)
            seen_node_ids.add(cast(int, current.pk))
            yield current
            current = current.parent

    def resolve_resource_ref(
        self,
        resource_ref: ACLResourceRef | tuple[str, str] | None,
    ) -> AclResourceNode | None:
        """Resolve one resource node from a small, bootstrap-friendly reference."""
        if resource_ref is None:
            return None
        normalized_ref = (
            resource_ref
            if isinstance(resource_ref, ACLResourceRef)
            else ACLResourceRef(resource_ref[0], resource_ref[1])
        )
        return AclResourceNode.objects.get(
            resource_type=normalized_ref.resource_type,
            resource_key=normalized_ref.resource_key,
        )

    def resolve_user(self, user_identifier: str) -> AbstractBaseUser:
        """Resolve one Django user by username or email."""
        user_model = get_user_model()
        lookup = (
            {"email": user_identifier}
            if "@" in user_identifier
            else {"username": user_identifier}
        )
        return cast("AbstractBaseUser", user_model.objects.get(**lookup))

    def summary(self) -> dict[str, int]:
        """Return created-row counters for command output."""
        return {
            "permissions": self.created_permissions,
            "groups": self.created_groups,
            "resources": self.created_resources,
            "memberships": self.created_memberships,
            "grants": self.created_grants,
        }


def load_bootstrap_object(path: str) -> object:
    """Load one object from `module.path:object_name` notation."""
    module_path, separator, attribute_name = path.partition(":")
    if not separator or not module_path or not attribute_name:
        msg = "Bootstrap paths must use the form 'module.path:object_name'."
        raise ValueError(msg)
    module = import_module(module_path)
    return getattr(module, attribute_name)
