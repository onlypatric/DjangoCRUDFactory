# DjangoACLBackend

`DjangoACLBackend` is the concrete ACL backend implementation used by
CRUDFactory in this repository.

It implements the [ACLBackend](ACLBackend.md) protocol.

## What It Does

It answers:

- global permission checks
- resource-scoped permission checks

by delegating to the Django ACL service layer.

## When To Use It

Use `DjangoACLBackend` when your project wants to use the built-in Django ORM
ACL implementation included with the library.

Typical pattern:

```python
from crudfactory import DjangoACLBackend, crud_acl


acl = crud_acl(
    backend=DjangoACLBackend(),
    permission_prefix="app.connector",
    resource_ref_from_instance=...,
)
```

## What It Depends On

It expects the ACL Django app models and tables to exist and be migrated.

That includes things like:

- permissions
- groups
- memberships
- resource nodes
- grants

## Relationship To DjangoACLService

`DjangoACLBackend` is the adapter used by CRUDFactory.

`DjangoACLService` is the lower-level service that contains the ACL evaluation
logic.
