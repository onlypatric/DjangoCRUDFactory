from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

__all__ = [
    "AclAuditLog",
    "AclEffect",
    "AclGrant",
    "AclGroup",
    "AclGroupMember",
    "AclPermission",
    "AclResourceClosure",
    "AclResourceNode",
    "AclSubjectKind",
]


class TimestampedModel(models.Model):
    """Small base class shared by the ACL catalog models."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AclSubjectKind(models.TextChoices):
    USER = "user", "User"
    GROUP = "group", "Group"


class AclEffect(models.TextChoices):
    ALLOW = "allow", "Allow"
    DENY = "deny", "Deny"


class AclPermission(TimestampedModel):
    """Canonical permission catalog entry used by the ACL engine."""

    permission_key = models.CharField(max_length=255, unique=True)
    domain = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "app_acl_permission"
        ordering = ["permission_key"]

    def __str__(self) -> str:
        return self.permission_key


class AclGroup(TimestampedModel):
    """ACL group that can receive grants and group members."""

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_acl_groups",
    )

    class Meta:
        db_table = "app_acl_group"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class AclGroupMember(models.Model):
    """Time-scoped membership connecting one user to one ACL group."""

    group = models.ForeignKey(
        AclGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="acl_group_memberships",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_acl_group_memberships",
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_acl_group_member"
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                name="app_acl_group_member_unique_group_user",
            ),
        ]


class AclResourceNode(TimestampedModel):
    """Persistent ACL resource tree node."""

    resource_type = models.CharField(max_length=100)
    resource_key = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    display_name = models.CharField(max_length=255, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "app_acl_resource_node"
        ordering = ["resource_type", "resource_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource_type", "resource_key"],
                name="app_acl_resource_node_unique_type_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.resource_type}:{self.resource_key}"


class AclResourceClosure(models.Model):
    """Materialized ancestor/descendant relation for the resource tree."""

    ancestor = models.ForeignKey(
        AclResourceNode,
        on_delete=models.CASCADE,
        related_name="descendant_links",
    )
    descendant = models.ForeignKey(
        AclResourceNode,
        on_delete=models.CASCADE,
        related_name="ancestor_links",
    )
    depth = models.PositiveIntegerField()

    class Meta:
        db_table = "app_acl_resource_closure"
        constraints = [
            models.UniqueConstraint(
                fields=["ancestor", "descendant"],
                name="app_acl_resource_closure_unique_pair",
            )
        ]


class AclGrant(TimestampedModel):
    """One allow/deny assignment to a user or group."""

    subject_kind = models.CharField(max_length=10, choices=AclSubjectKind.choices)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="acl_user_grants",
    )
    subject_group = models.ForeignKey(
        AclGroup,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    permission = models.ForeignKey(
        AclPermission,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    resource = models.ForeignKey(
        AclResourceNode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    effect = models.CharField(max_length=10, choices=AclEffect.choices)
    priority = models.SmallIntegerField(default=0)
    conditions = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_acl_grants",
    )

    class Meta:
        db_table = "app_acl_grant"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(subject_kind=AclSubjectKind.USER)
                        & Q(subject_user__isnull=False)
                        & Q(subject_group__isnull=True)
                    )
                    | (
                        Q(subject_kind=AclSubjectKind.GROUP)
                        & Q(subject_group__isnull=False)
                        & Q(subject_user__isnull=True)
                    )
                ),
                name="app_acl_grant_valid_subject_columns",
            )
        ]


class AclAuditLog(models.Model):
    """Administrative ACL audit trail."""

    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acl_audit_events",
    )
    event_type = models.CharField(max_length=100)
    subject_kind = models.CharField(
        max_length=10,
        choices=AclSubjectKind.choices,
        null=True,
        blank=True,
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acl_audit_subject_user_events",
    )
    subject_group = models.ForeignKey(
        AclGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acl_audit_subject_group_events",
    )
    permission = models.ForeignKey(
        AclPermission,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    resource = models.ForeignKey(
        AclResourceNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_acl_audit_log"
