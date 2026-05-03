# Feature Request: Soft Delete, Restore, And Archive Lifecycles

## Summary

`CRUDFactory` should support first-class soft delete / restore / archive
lifecycles instead of only hard delete.

This is one of the most common production requirements that still pushes teams
into custom views and custom model-specific endpoints.

## Problem

Current CRUDFactory delete behavior is fundamentally:

- hard delete by default
- or explicit custom logic in a handler/action

But many real systems need:

- archive instead of delete
- restore archived rows
- exclude archived rows from normal list routes
- optionally include archived rows when explicitly requested

Without this, teams still need to hand-build:

- archive endpoints
- restore endpoints
- alternate querysets
- repeated “active only” filtering logic

## Desired Capability

A factory should be able to say:

```python
factory = CRUDFactory(
    model=Item,
    ...,
    lifecycle=soft_delete_lifecycle(
        deleted_field="deleted_at",
        restore_action=True,
        list_mode="active-only",
    ),
)
```

Or:

```python
archive_lifecycle(
    archived_field="archived_at",
    archived_by_field="archived_by",
    restore_action=True,
)
```

## Required Behavior

- normal list excludes archived rows by default
- detail endpoints can be configured to:
  - hide archived rows
  - or allow explicit retrieval
- `DELETE` marks the row as archived instead of deleting it
- optional restore action unarchives the row
- docs/schema make lifecycle semantics explicit

## Why This Matters

This is routine product behavior:

- users deactivate records
- admins restore mistakenly removed rows
- systems retain audit history
- business rules forbid destructive deletion

If CRUDFactory cannot express this, many otherwise ordinary resources still
need custom views.

## V1 Scope

Support:

- timestamp-based soft delete
- boolean archive flag
- optional restore detail action
- default active-only list behavior
- optional `include_archived` query param

V1 does not need:

- full audit/version recovery
- arbitrary custom lifecycle graphs

## Suggested Implementation Direction

- add lifecycle config object
- customize delete behavior in generated viewset
- inject default queryset filtering for active rows
- optionally register a restore custom action

## Test Plan

- delete archives the row instead of removing it
- archived rows disappear from normal lists
- restore action reactivates the row
- optional include-archived query path works
- ACL still applies correctly
- docs/schema describe archive semantics

## Assumptions

- V1 should focus on the common “archived/deleted” lifecycle, not full workflow
  state machines
- explicit lifecycle config is better than guessing from model field names
