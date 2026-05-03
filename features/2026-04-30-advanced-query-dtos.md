# Feature Request: Advanced Query DTOs

## Summary

`CRUDFactory` should support richer query DTOs for collection reads so teams can
express more complex search behavior without abandoning the factory.

Today flat field-based filtering is useful, but many real applications need
slightly more power:

- date ranges
- “one of these statuses”
- text search
- include / exclude semantics
- OR groups
- simple domain-specific query forms

## Problem

The current filter metadata is good for:

- exact field filters
- lookup-based field filters
- ordering

But it is still fundamentally flat and row-oriented.

As soon as a team needs a “real search form” for a list screen, they often
switch to a hand-built DRF view because they want:

- one query DTO
- richer validation
- explicit response contract
- custom queryset logic

CRUDFactory should be able to own more of that space.

## Desired Capability

Support dedicated query DTOs for list endpoints, not just grouped actions.

Example:

```python
@dataclass
class ConnectorQueryDTO:
    status_in: list[str] | None = query_list("status")
    search: str | None = full_text_search(fields=("name", "serial_number"))
    min_power_kw: float | None = query_range("max_power_kw", op="gte")
    max_power_kw: float | None = query_range("max_power_kw", op="lte")
    updated_after: datetime | None = query_range("updated_at", op="gte")
```

And then:

```python
factory = CRUDFactory(
    model=Connector,
    ...,
    list_query=ConnectorQueryDTO,
)
```

## Capability Areas

Potential helpers:

- `query_filter(...)`
- `query_list(...)`
- `query_range(...)`
- `query_search(...)`
- `query_exclude(...)`
- `query_ordering(...)`

And eventually:

- grouped OR filters
- reusable named filter packs

## Why This Matters

A large percentage of backend endpoints are not “plain CRUD” in the naïve
sense. They are “CRUD plus serious list querying”.

If CRUDFactory can model that well, it becomes a much more viable default for:

- admin panels
- backoffice data exploration
- operations dashboards
- catalog management
- monitoring/search screens

## V1 Scope

Start with:

- dedicated list query DTOs
- scalar equality/range/search/list filters
- explicit ordering field
- no nested Boolean expression trees yet

That already covers most real screens.

## Suggested Implementation Direction

- reuse the dataclass serializer pipeline for query params
- build a separate query-metadata layer for list endpoints
- compose this with existing filter/order behavior rather than replacing it

## Test Plan

- list query DTO validates query params
- list filters narrow queryset correctly
- list search spans configured text fields
- list ordering comes from query DTO rather than raw request strings
- invalid query params return DRF-style `400`
- schema/docs show query DTO fields as query parameters

## Assumptions

- the library should keep the current simple filter metadata for low-friction
  cases
- advanced query DTOs should be opt-in, not mandatory
