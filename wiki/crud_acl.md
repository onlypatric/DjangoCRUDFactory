# crud_acl

`crud_acl(...)` is the convenience helper for factory-level ACL wiring.

It builds an `ACLConfig` using the default CRUD permission naming convention.

## Default Permission Mapping

Given:

```python
crud_acl(permission_prefix="app.connector", ...)
```

the helper maps actions like this:

- `list` -> `app.connector.read`
- `retrieve` -> `app.connector.read`
- `create` -> `app.connector.create`
- `update` -> `app.connector.update`
- `partial_update` -> `app.connector.update`
- `destroy` -> `app.connector.delete`

## Typical Usage

```python
from crudfactory import DjangoACLBackend, crud_acl


factory = CRUDFactory(
    model=Connector,
    create_input=ConnectorCreateDTO,
    update_input=ConnectorUpdateDTO,
    partial_update_input=ConnectorPatchDTO,
    acl=crud_acl(
        backend=DjangoACLBackend(),
        permission_prefix="app.connector",
        resource_ref_from_instance=connector_resource_ref,
        resource_ref_from_create_input=create_resource_ref,
        resource_ref_from_update_input=update_resource_ref,
        resource_ref_from_patch_input=patch_resource_ref,
    ),
)
```

## Important Parameters

- `backend`
  The ACL backend implementation.

- `permission_prefix`
  Prefix used to build permission keys.

- `mode`
  One of:
  - `scoped`
  - `global`
  - `disabled`

- `unauthorized_as_404`
  Controls whether object-level deny becomes `404` instead of `403`.

- `list_filter_mode`
  Controls whether unauthorized list results are filtered or the whole request
  is forbidden.

- `resource_ref_from_instance`
- `resource_ref_from_create_input`
- `resource_ref_from_update_input`
- `resource_ref_from_patch_input`

  These tell CRUDFactory how to resolve the target ACL resource for each CRUD
  phase.

## Related Pages

- [ACLConfig](ACLConfig.md)
- [ACLBackend](ACLBackend.md)
- [Home](Home.md)
