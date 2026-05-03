# Feature Request: Generated Field Subresource Endpoints

## Summary

`CRUDFactory` should support generated field-level endpoints for model fields
that need to be exposed as their own subresource, especially:

- `JSONField`
- metadata dictionaries
- display configuration blobs
- large text/config fields that deserve a dedicated endpoint

Typical target routes:

- `GET /resource/{id}/metadata/`
- `PATCH /resource/{id}/metadata/`

## Problem

This pattern is extremely common, but it still forces custom APIView code:

- read only one field
- patch only one field
- optionally merge dictionaries instead of replacing them
- use separate ACL rules from the main resource

That is CRUD-adjacent, but today it still lives outside the factory.

## Desired Capability

A factory should be able to declare:

```python
factory.field_endpoint(
    field_name="metadata",
    methods=("get", "patch"),
    patch_mode="merge",
    read_permission="app.ocpp.station.read",
    update_permission="app.ocpp.station.display.update",
)
```

Or a more explicit configuration form:

```python
field_subresource(
    field_name="metadata",
    response_dataclass=MetadataResponseDTO,
    patch_input=MetadataPatchDTO,
    patch_mode="merge",
    acl=...,
)
```

## Required Behavior

- `GET` returns only the field payload
- `PATCH` updates only the field payload
- optional patch strategies:
  - `replace`
  - `merge`
- schema/docs reflect the field-specific contract
- ACL can differ from the parent resource CRUD ACL

## Why This Matters

These endpoints are not unusual edge cases. They show up constantly in:

- metadata editors
- UI/display configuration endpoints
- settings/config APIs
- tag dictionaries
- freeform integration payloads

If CRUDFactory cannot generate them, teams still end up writing avoidable
APIView boilerplate.

## V1 Scope

Support:

- detail-scoped field endpoints only
- `GET`
- `PATCH`
- dictionary merge semantics for dict-like fields
- replace semantics for simple fields

V1 does not need:

- list-scoped field endpoints
- streaming/binary subresources
- nested arbitrary field trees

## Suggested Implementation Direction

- add a new field subresource spec
- register extra detail actions under predictable URLs
- serialize the field payload through a small dataclass or serializer wrapper
- support merge/replace patch strategies

## Test Plan

- get metadata subresource returns only the field payload
- patch replace updates only the field
- patch merge merges dictionaries correctly
- unrelated model fields remain untouched
- field endpoint ACL differs cleanly from base CRUD ACL
- schema/docs include field subresource contracts

## Assumptions

- V1 should target the common JSON/dict field use case first
- explicit field endpoint config is better than trying to infer user intent from
  model field type alone
