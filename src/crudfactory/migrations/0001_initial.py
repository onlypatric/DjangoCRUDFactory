from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AclPermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("permission_key", models.CharField(max_length=255, unique=True)),
                ("domain", models.CharField(max_length=100)),
                ("action", models.CharField(max_length=100)),
                ("resource_type", models.CharField(blank=True, default="", max_length=100)),
                ("description", models.TextField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "app_acl_permission",
                "ordering": ["permission_key"],
            },
        ),
        migrations.CreateModel(
            name="AclGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True, null=True)),
                ("is_system", models.BooleanField(default=False)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_acl_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "app_acl_group",
                "ordering": ["code"],
            },
        ),
        migrations.CreateModel(
            name="AclResourceNode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resource_type", models.CharField(max_length=100)),
                ("resource_key", models.CharField(max_length=255)),
                ("display_name", models.CharField(blank=True, max_length=255, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="crudfactory.aclresourcenode",
                    ),
                ),
            ],
            options={
                "db_table": "app_acl_resource_node",
                "ordering": ["resource_type", "resource_key"],
            },
        ),
        migrations.CreateModel(
            name="AclGroupMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "added_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_acl_group_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="crudfactory.aclgroup",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acl_group_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "app_acl_group_member",
            },
        ),
        migrations.CreateModel(
            name="AclResourceClosure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("depth", models.PositiveIntegerField()),
                (
                    "ancestor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="descendant_links",
                        to="crudfactory.aclresourcenode",
                    ),
                ),
                (
                    "descendant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ancestor_links",
                        to="crudfactory.aclresourcenode",
                    ),
                ),
            ],
            options={
                "db_table": "app_acl_resource_closure",
            },
        ),
        migrations.CreateModel(
            name="AclGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject_kind", models.CharField(choices=[("user", "User"), ("group", "Group")], max_length=10)),
                ("effect", models.CharField(choices=[("allow", "Allow"), ("deny", "Deny")], max_length=10)),
                ("priority", models.SmallIntegerField(default=0)),
                ("conditions", models.JSONField(blank=True, default=dict)),
                ("enabled", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_acl_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grants",
                        to="crudfactory.aclpermission",
                    ),
                ),
                (
                    "resource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grants",
                        to="crudfactory.aclresourcenode",
                    ),
                ),
                (
                    "subject_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grants",
                        to="crudfactory.aclgroup",
                    ),
                ),
                (
                    "subject_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acl_user_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "app_acl_grant",
            },
        ),
        migrations.CreateModel(
            name="AclAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=100)),
                ("subject_kind", models.CharField(blank=True, choices=[("user", "User"), ("group", "Group")], max_length=10, null=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acl_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="crudfactory.aclpermission",
                    ),
                ),
                (
                    "resource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="crudfactory.aclresourcenode",
                    ),
                ),
                (
                    "subject_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acl_audit_subject_group_events",
                        to="crudfactory.aclgroup",
                    ),
                ),
                (
                    "subject_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acl_audit_subject_user_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "app_acl_audit_log",
            },
        ),
        migrations.AddConstraint(
            model_name="aclgroupmember",
            constraint=models.UniqueConstraint(fields=("group", "user"), name="app_acl_group_member_unique_group_user"),
        ),
        migrations.AddConstraint(
            model_name="aclresourcenode",
            constraint=models.UniqueConstraint(fields=("resource_type", "resource_key"), name="app_acl_resource_node_unique_type_key"),
        ),
        migrations.AddConstraint(
            model_name="aclresourceclosure",
            constraint=models.UniqueConstraint(fields=("ancestor", "descendant"), name="app_acl_resource_closure_unique_pair"),
        ),
        migrations.AddConstraint(
            model_name="aclgrant",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            subject_kind="user",
                            subject_user__isnull=False,
                            subject_group__isnull=True,
                        )
                    )
                    | (
                        models.Q(
                            subject_kind="group",
                            subject_group__isnull=False,
                            subject_user__isnull=True,
                        )
                    )
                ),
                name="app_acl_grant_valid_subject_columns",
            ),
        ),
    ]
