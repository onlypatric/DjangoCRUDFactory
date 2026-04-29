# DjangoACLService

`DjangoACLService` is the service-layer implementation behind the Django ACL
backend.

## Purpose

It contains the real ACL evaluation behavior used by:

- `DjangoACLBackend`
- ACL bootstrap workflows
- ACL-related integration logic

## What It Typically Handles

Depending on the call, the service is responsible for things such as:

- resolving group memberships
- evaluating grants
- respecting allow/deny semantics
- handling resource hierarchy logic
- applying precedence rules
- checking time-scoped rules

## Who Uses It

Most CRUDFactory app code does not use `DjangoACLService` directly.

The common pattern is:

- app code configures `crud_acl(...)`
- `crud_acl(...)` uses `DjangoACLBackend`
- `DjangoACLBackend` delegates to `DjangoACLService`

## When You Might Use It Directly

Direct use is more likely if you are:

- building admin tools
- running ACL audits
- writing bootstrap/maintenance scripts
- testing ACL decisions outside CRUDFactory
