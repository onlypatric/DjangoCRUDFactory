# ACLBackend

`ACLBackend` is the protocol CRUDFactory uses to ask authorization questions.

It is not a concrete implementation by itself.

## Purpose

CRUDFactory stays generic by depending on a small backend contract instead of a
hard-coded permission engine.

Any backend used by CRUDFactory must be able to answer:

- global permission checks
- resource-scoped permission checks

## Required Methods

### `has_permission(actor, permission) -> bool`

Checks whether an actor has a global permission.

### `has_permission_on_resource(actor, permission, resource_ref) -> bool`

Checks whether an actor has a permission on a specific resource reference.

## What Counts As `actor`

In most Django projects this will be:

- `request.user`

But the protocol intentionally keeps it generic, so a backend can also support:

- service accounts
- custom principal objects
- tenant-scoped actors

## What Counts As `resource_ref`

CRUDFactory treats `resource_ref` as an opaque object.

The most common concrete type in this repository is:

- [ACLResourceRef](ACLResourceRef.md)

## When You Use This Directly

Usually you do not instantiate or implement `ACLBackend` inline in app code.

Instead you use a concrete implementation like:

- [DjangoACLBackend](DjangoACLBackend.md)

and pass it through `crud_acl(...)`.
