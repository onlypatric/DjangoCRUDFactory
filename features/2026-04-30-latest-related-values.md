# Feature Request: Latest Related Row Helpers

## Summary

`CRUDFactory` should support response fields that come from the **latest row in a
related history table**, without forcing users to hand-write queryset
annotations for each endpoint.

This is a very common pattern in monitoring, telemetry, pricing, audit, and
history-driven products.

This request is intentionally narrower than
`2026-04-30-declarative-annotation-fields.md`. That broader request should
provide the general annotation/subquery mechanism; this request focuses on one
of the most valuable first-class wrappers built on top of it.

## Problem

The current library can already expose annotated fields if the user manually
builds the queryset. So this is possible today:

- annotate `Item` with `latest_value`
- map `latest_value` into a response dataclass

But the abstraction is still too low-level. Every user has to reinvent:

- `Subquery`
- `OuterRef`
- ordering field choice
- null handling
- scalar vs nested latest-row mapping

That is exactly the kind of repeated ORM plumbing the factory should absorb.

## Typical Use Case

- `Item` has many `HistoryValueNew`
- response should include:
  - `itemid`
  - `description`
  - `latest_value: float | None`

Or:

- `latest_reading.value`
- `latest_reading.recorded_at`
- `latest_reading.quality`

## Proposed Public API

Scalar helper:

```python
latest_value: float | None = latest_related_value(
    relation="history_values",
    value_field="value",
    order_by="-recorded_at",
)
```

Nested helper:

```python
latest_reading: LatestReadingDTO | None = latest_related_object(
    relation="history_values",
    order_by="-recorded_at",
)
```

Alternative explicit model-oriented form:

```python
latest_value: float | None = latest_related_value(
    model=Historyvalue_new,
    fk_field="item",
    value_field="value",
    order_by="-id",
)
```

## Required Behavior

- annotate the root queryset automatically
- inject the resolved value into the response DTO
- support `None` when no related row exists
- work for list and detail endpoints
- document the latest-related field in OpenAPI and Markdown docs

## V1 Scope

Support:

- scalar latest field extraction
- optional nested latest object DTO
- ordering by one or more fields
- nullable result when no row exists

V1 does **not** need:

- arbitrary aggregate windows
- multiple latest rows
- partitioning by custom groups beyond the root model relation

## Why This Matters

This pattern shows up constantly:

- latest telemetry
- latest sensor reading
- latest market price
- latest software heartbeat
- latest event status
- latest audit result

If CRUDFactory can handle this declaratively, a lot of “read-only but slightly
special” endpoints stop needing custom query code.

## Suggested Implementation Direction

- add response metadata helpers describing the latest-related lookup
- generate stable annotation aliases
- build queryset annotations using `Subquery` and `OuterRef`
- support scalar extraction and nested-object mapping

## Test Plan

- list endpoint returns latest scalar value
- detail endpoint returns latest scalar value
- no-history rows return `null`
- nested latest object returns all declared fields
- multiple latest-related fields can coexist
- invalid config fails clearly at factory construction
- schema/docs include the field as a normal response field

## Assumptions

- the feature should require an explicit ordering definition
- “latest” must never be inferred implicitly without an order field
- the user should still be able to fall back to manual queryset annotations for
  unusual cases
