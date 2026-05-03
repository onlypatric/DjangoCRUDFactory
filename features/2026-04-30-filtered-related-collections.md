# Feature Request: Declarative Filtered Related Collections And Prefetch Specs

## Summary

`CRUDFactory` should let response declarations describe not only nested related
lists, but also the queryset or prefetch strategy used to load them.

This keeps nested response shape and nested loading logic closer together.

## Problem

Nested response DTOs are already possible, but the queryset tuning still often
lives in separate helpers:

- custom `Prefetch(...)`
- nested queryset builders
- detail-specific child querysets

That is not terrible, but it still spreads one conceptual unit across too many
places:

- response structure in one file section
- nested loading strategy in another helper
- prefetch graph in the queryset declaration

## Desired Capability

Support declarations like:

```python
chargepoints: list[ChargepointDetailResponse] = field(
    default_factory=list,
    metadata=related_list(
        "chargepoints",
        queryset=visible_chargepoints().prefetch_related(...),
    ),
)
```

Or a more factory-oriented API:

```python
factory.prefetch(
    "chargepoints",
    queryset=chargepoint_detail_queryset(),
)
```

## Required Behavior

- declare filtered or tuned prefetches explicitly
- tie nested response list fields to nested loading plans
- support normal `Prefetch(...)` semantics under the hood
- compose cleanly with existing response mapping

## Why This Matters

This improves:

- readability
- maintainability
- correctness of nested detail endpoints

It is especially useful once nested response DTOs become deeper and more
specialized.

## Relationship To Other Requests

- `2026-04-30-queryset-plans-from-response-contracts.md` is more inference- and
  safety-oriented.
- this request is about explicit, declarative nested loading control.

## Suggested Implementation Direction

- extend nested response metadata with optional queryset/prefetch hints
- build `Prefetch(...)` objects automatically when the factory assembles the
  base queryset
- allow explicit overrides where inference is not enough

## Test Plan

- nested related list can declare a filtered queryset
- prefetch strategy applies to list and detail endpoints
- nested response still serializes correctly
- declared prefetch does not break existing stat annotations or related field
  mapping

## Assumptions

- V1 should focus on `Prefetch(...)`-compatible related list declarations
- explicit declaration is more important than clever inference here
