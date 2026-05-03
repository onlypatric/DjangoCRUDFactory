# Feature Request: Declarative Annotation And Subquery Fields

## Summary

`CRUDFactory` should support response fields backed by declarative queryset
annotations and correlated subqueries, not just plain model attributes and
aggregate stats.

This is the general feature. “Latest related value” is one especially common
subcase of it.

## Problem

The library already handles:

- direct model fields
- related scalar fields through mapping
- aggregate count/sum/avg/min/max stats

But many useful response fields are neither direct attributes nor aggregates.
They are derived per root row with:

- `annotate(...)`
- `Subquery(...)`
- `OuterRef(...)`
- `Case/When(...)`
- `Exists(...)`

Today users must hand-build those querysets themselves, which means repeated
ORM glue outside the response contract.

## Desired Capability

Allow response DTOs to declare annotated fields close to where they are used.

Low-level shape:

```python
latest_value: float | None = field(
    metadata=annotated_field(
        alias="latest_value",
        annotation=Subquery(...),
    )
)
```

Safer higher-level wrappers could sit on top of that for common patterns.

## Common Use Cases

- latest child row value
- first child timestamp
- most recent heartbeat timestamp
- derived status from latest event row
- boolean existence flags
- scalar values from a correlated child row

## V1 Scope

Support:

- declarative annotations on response fields
- stable internal aliases
- scalar annotation fields
- `Subquery`, `Exists`, `Case`, and other normal Django expressions
- response injection from annotated values

V1 does not need:

- arbitrary user-defined Python post-processing inside the metadata itself
- auto-generated schema descriptions from opaque expressions

## Why This Matters

This feature would remove a large amount of “special read endpoint” boilerplate
from real backends:

- monitoring
- telemetry
- pricing
- status dashboards
- audit summaries

It is a high-leverage capability because it unlocks many custom read views with
one abstraction.

## Relationship To Other Requests

- `2026-04-30-latest-related-values.md` is a high-value specialized wrapper on
  top of this capability.
- `2026-04-30-queryset-plans-from-response-contracts.md` could later build on
  this and incorporate derived annotations into a broader plan.

## Suggested Implementation Direction

- add a response metadata helper for declarative annotations
- collect annotation specs during factory construction
- annotate the queryset automatically
- inject annotation aliases into the mapped response DTO

## Test Plan

- annotated scalar fields appear in list responses
- annotated scalar fields appear in detail responses
- multiple annotation fields coexist correctly
- invalid annotation config fails clearly
- schema/docs include the field as a normal response field
- existing stat metadata and related field mapping remain compatible

## Assumptions

- V1 should expose Django expression power, not try to invent a completely new
  mini-language
- the library should still offer higher-level wrappers for common patterns once
  the base abstraction exists
