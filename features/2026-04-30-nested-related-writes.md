# Feature Request: Nested Related Writes

## Summary

`CRUDFactory` should support typed create, update, and patch flows that write a
root model **plus one or more related model collections** in the same request.

This is the single biggest remaining reason to drop down to hand-written DRF
views.

Examples:

- create a `Location` together with its initial `Chargepoint[]`
- create a `Chargepoint` together with its `Connector[]`
- update a parent and replace or merge a child collection
- patch only selected nested child rows

## Problem

Today `CRUDFactory` handles one root model very well:

- typed request DTOs
- typed response DTOs
- simple auto-writes
- explicit custom write handlers
- nested read responses

But the write side is still mostly **single-model oriented**.

As soon as a user needs any of these:

- create parent + children
- update parent + children together
- delete child rows not present in payload
- upsert child rows by ID or natural key
- validate nested request collections

they are forced into custom handlers or a hand-written view.

That is a real product-level gap, not a niche feature.

## Desired Capability

Allow nested request DTOs to describe related writes declaratively.

Example target shape:

```python
@dataclass
class ConnectorWriteDTO:
    name: str
    status: str
    max_power_kw: float


@dataclass
class ChargepointWriteDTO:
    name: str
    serial_number: str
    connectors: list[ConnectorWriteDTO]
```

Then:

```python
factory = CRUDFactory(
    model=Chargepoint,
    create_input=ChargepointWriteDTO,
    update_input=ChargepointWriteDTO,
    partial_update_input=ChargepointPatchDTO,
    nested_writes=[...],
)
```

## Proposed Public API

Add a nested write configuration layer, for example:

```python
nested_relation(
    field_name="connectors",
    relation_name="connectors",
    mode="replace",
    match_by="id",
)
```

Possible root config:

```python
factory = CRUDFactory(
    ...,
    nested_writes=[
        nested_relation(
            field_name="connectors",
            relation_name="connectors",
            mode="replace",
            match_by="id",
        ),
    ],
)
```

Or, if the library wants to keep a more metadata-driven style:

```python
@dataclass
class ChargepointWriteDTO:
    name: str
    serial_number: str
    connectors: list[ConnectorWriteDTO] = nested_write(
        relation_name="connectors",
        mode="replace",
        match_by="id",
    )
```

## V1 Scope

Start with the useful core:

- `one-to-many` child collections only
- root model already chosen by the factory
- child rows written transactionally
- configurable modes:
  - `create-only`
  - `replace`
  - `merge`
- optional child matching by:
  - primary key
  - natural key field

V1 does **not** need to solve:

- arbitrary many-to-many graphs
- deeply recursive trees with unlimited nesting
- polymorphic relations

## Validation Requirements

The feature must validate:

- nested dataclass request shapes
- unsupported child field types
- duplicate child keys in the same payload
- illegal `replace` payloads without a stable match key
- write modes that are incompatible with the relation type

## Behavioral Questions The Feature Must Answer

- if a child row is missing from `replace`, should it be deleted?
- if a child row has no ID, should it be created?
- if a child ID is unknown, should it fail or create?
- how should patch semantics work for child collections?
- should nested writes be all-or-nothing in one transaction?

The answer should be explicit and configurable, not inferred implicitly.

## Why This Matters

Without this feature, CRUDFactory still leaves out a huge class of real admin
and operational APIs:

- inventory with nested attributes
- stations with nested devices
- orders with nested line items
- surveys with nested questions
- forms with nested fields

These are not edge cases. They are normal business CRUD.

## Suggested Implementation Direction

- add a nested write config model
- build nested serializers from nested dataclasses
- convert nested validated payloads into nested dataclass instances
- run writes inside a transaction
- split responsibilities into:
  - root write
  - child relation reconciliation
  - deletion / update / creation planning

## Test Plan

- create parent with child collection
- full update replacing child collection
- merge update preserving untouched child rows
- patch parent without touching child rows
- patch selected child rows only
- duplicate child keys fail clearly
- invalid nested payload returns DRF-style `400`
- response DTO includes updated nested output after write
- ACL and permissions still apply to the root endpoint

## Assumptions

- this feature should compose with existing explicit write hooks
- the library should still allow manual escape hatches for domain-specific
  write logic
- V1 should optimize for the 80 percent case, not arbitrary graph persistence
