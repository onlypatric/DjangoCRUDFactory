# Feature Request: Bulk Typed Operations

## Summary

`CRUDFactory` should support first-class bulk create, bulk update, bulk patch,
and bulk delete endpoints with typed dataclasses, predictable response
contracts, and optional row-level ACL.

Bulk APIs are one of the most common remaining reasons to write custom views.

## Problem

Today `CRUDFactory` is strong at one-resource-at-a-time CRUD and custom
actions. But many operational products need:

- import 500 rows
- patch many rows in one request
- archive many rows by ID
- run validation per row and return a structured result

The current custom action system can approximate this, but it leaves too much
manual work:

- body parsing conventions
- per-row validation orchestration
- partial success result format
- bulk ACL behavior
- schema and docs consistency

## Desired Capability

Expose bulk endpoints as first-class typed factory capabilities.

Example:

```python
factory = CRUDFactory(
    model=Connector,
    ...,
    bulk_actions=[
        bulk_create_action(...),
        bulk_patch_action(...),
        bulk_delete_action(...),
    ],
)
```

Or a more opinionated helper:

```python
factory = CRUDFactory(
    model=Connector,
    create_input=ConnectorCreateDTO,
    update_input=ConnectorUpdateDTO,
    partial_update_input=ConnectorPatchDTO,
    bulk=bulk_crud(
        create=True,
        patch=True,
        delete=True,
    ),
)
```

## Important Product Decisions

The feature must make bulk behavior explicit:

- all-or-nothing vs partial success
- row identity for update and patch
- result shape for success and failure
- ACL handling:
  - fail whole request
  - filter unauthorized rows
  - return per-row denial results

These behaviors should be configurable, not hidden.

## Proposed Response Contract Pattern

Structured result payloads like:

```python
@dataclass
class BulkRowErrorDTO:
    index: int
    identifier: str | None
    errors: dict[str, list[str]]


@dataclass
class BulkMutationResultDTO:
    created: int
    updated: int
    deleted: int
    failed: int
    errors: list[BulkRowErrorDTO]
```

Or for success rows:

```python
@dataclass
class BulkPatchResultDTO:
    succeeded_ids: list[int]
    failed: list[BulkRowErrorDTO]
```

## V1 Scope

The most valuable initial capabilities:

- `POST /bulk-create/`
- `PATCH /bulk-patch/`
- `DELETE /bulk-delete/`
- typed input lists
- typed structured result
- optional transaction mode:
  - `atomic`
  - `best-effort`

## Why This Matters

Without bulk support, teams still need manual views for:

- imports
- table actions
- admin dashboards
- field migrations triggered from the product
- mass status changes
- archive / restore flows

That is exactly the kind of repetitive backend code CRUDFactory should absorb.

## Suggested Implementation Direction

- introduce bulk action spec types separate from normal custom actions
- reuse request dataclass validation per row
- support configurable transaction strategies
- expose explicit result DTOs
- integrate with OpenAPI and generated docs

## Test Plan

- bulk create success
- bulk patch success
- bulk delete success
- invalid row validation returns structured error
- atomic mode rolls back all rows on one failure
- best-effort mode commits valid rows and reports invalid rows
- scoped ACL filters or denies rows according to config
- schema output shows list payloads and result DTOs
- docs generator includes bulk routes and behavior notes

## Assumptions

- V1 can focus on flat row lists, not nested bulk graph mutation
- explicit result DTOs are better than ad-hoc DRF error shapes for bulk
- this should reuse the existing dataclass serializer pipeline, not reinvent it
