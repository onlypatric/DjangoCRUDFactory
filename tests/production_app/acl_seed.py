from __future__ import annotations

from crudfactory import (
    ACLBootstrapper,
    ACLGroupSeed,
    ACLPermissionSeed,
    ACLResourceRef,
    ACLResourceSeed,
)

ACL_PERMISSION_SEEDS = [
    ACLPermissionSeed(
        permission_key="app.admin.full",
        domain="admin",
        action="full",
    ),
    ACLPermissionSeed(
        permission_key="app.location.read",
        domain="ev",
        action="read",
        resource_type="location",
    ),
    ACLPermissionSeed(
        permission_key="app.location.update",
        domain="ev",
        action="update",
        resource_type="location",
    ),
    ACLPermissionSeed(
        permission_key="app.chargepoint.read",
        domain="ev",
        action="read",
        resource_type="chargepoint",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.read",
        domain="ev",
        action="read",
        resource_type="connector",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.create",
        domain="ev",
        action="create",
        resource_type="connector",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.update",
        domain="ev",
        action="update",
        resource_type="connector",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.delete",
        domain="ev",
        action="delete",
        resource_type="connector",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.start",
        domain="ev",
        action="start",
        resource_type="connector",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.stop",
        domain="ev",
        action="stop",
        resource_type="connector",
    ),
    ACLPermissionSeed(
        permission_key="app.connector.unlock",
        domain="ev",
        action="unlock",
        resource_type="connector",
    ),
]

ACL_GROUP_SEEDS = [
    ACLGroupSeed(
        code="ops-admins",
        name="Operations Admins",
        description="Operational administrators with read access to seeded resources.",
        is_system=True,
    )
]

ACL_RESOURCE_SEEDS = [
    ACLResourceSeed(
        resource_type="location",
        resource_key="rome-hub",
        display_name="Rome Hub",
    ),
    ACLResourceSeed(
        resource_type="chargepoint",
        resource_key="rome-hub/cp-01",
        display_name="Rome Hub Chargepoint 01",
        parent_ref=ACLResourceRef("location", "rome-hub"),
    ),
    ACLResourceSeed(
        resource_type="connector",
        resource_key="rome-hub/cp-01/connector-1",
        display_name="Rome Hub Connector 1",
        parent_ref=ACLResourceRef("chargepoint", "rome-hub/cp-01"),
    ),
]


def bootstrap_acl_demo(bootstrapper: ACLBootstrapper) -> str:
    """Seed a small but realistic ACL catalog and resource tree for tests."""
    bootstrapper.ensure_permissions(ACL_PERMISSION_SEEDS)
    bootstrapper.ensure_groups(ACL_GROUP_SEEDS)
    bootstrapper.ensure_resources(ACL_RESOURCE_SEEDS)
    bootstrapper.ensure_group_grant(
        group_code="ops-admins",
        permission_key="app.location.read",
        resource_ref=ACLResourceRef("location", "rome-hub"),
    )
    bootstrapper.ensure_group_grant(
        group_code="ops-admins",
        permission_key="app.chargepoint.read",
        resource_ref=ACLResourceRef("chargepoint", "rome-hub/cp-01"),
    )
    bootstrapper.ensure_group_grant(
        group_code="ops-admins",
        permission_key="app.connector.read",
        resource_ref=ACLResourceRef("connector", "rome-hub/cp-01/connector-1"),
    )
    bootstrapper.ensure_group_grant(
        group_code="ops-admins",
        permission_key="app.connector.start",
        resource_ref=ACLResourceRef("connector", "rome-hub/cp-01/connector-1"),
    )
    return "Seeded ACL demo catalog, resource tree, and reader grants."
