# Feature Request: Queryset Plans Derived From Response Contracts

## Summary

`CRUDFactory` should be able to derive or assist with `select_related`,
`prefetch_related`, and common annotations from the declared response
dataclasses.

This would remove a large amount of repetitive queryset plumbing and make
generated endpoints safer by default against avoidable N+1 patterns.

## Problem

Today the response side is already strongly typed, but users still often need
to hand-build querysets that mirror the response shape:

- `select_related("location")`
- `prefetch_related("connectors")`
- annotate counts or related scalar data

That logic is both repetitive and easy to get wrong. If a response DTO clearly
references:

- `chargepoint__location__name`
- `connectors: list[ConnectorDTO]`

then a lot of the necessary queryset plan can be inferred or at least declared
in one place rather than manually rebuilt for every factory.

## Desired Capability

At minimum, expose a query-plan helper:

```python
factory = CRUDFactory(
    model=Chargepoint,
    response_dataclass=ChargepointResponseDTO,
    query_plan=auto_query_plan(),
)
```

Or:

```python
query_plan = derive_query_plan(ChargepointResponseDTO)
```

Possible behaviors:

- infer `select_related` chains from scalar related fields
- infer `prefetch_related` chains from nested response lists
- attach stat annotations already declared in response metadata
- allow manual overrides

## Why This Matters

This feature is valuable for two reasons:

1. developer ergonomics
   Users describe the response once and do not keep re-encoding the same graph
   in queryset code.

2. safety
   It becomes harder to accidentally ship response DTOs that cause N+1 query
   behavior in list endpoints.

## V1 Scope

Support:

- related scalar field path inference for `select_related`
- related list inference for `prefetch_related`
- stat annotation attachment from already-supported stat metadata
- manual opt-out and overrides

V1 does not need:

- perfect inference for every ORM edge case
- arbitrary conditional prefetch plans
- automatic performance magic without explicit escape hatches

## Suggested Implementation Direction

- inspect response dataclass metadata and type hints
- gather relation paths used by:
  - `model_field(...)`
  - nested dataclass lists
  - stat metadata
- derive a query plan object
- merge the auto plan with user-provided queryset customizations

## Test Plan

- response DTO with related scalar fields yields expected `select_related`
- nested child list yields expected `prefetch_related`
- stats metadata attaches annotations into the same plan
- manual queryset still overrides auto plan when supplied
- generated endpoint returns correct data with fewer queries than an unplanned
  equivalent fixture

## Assumptions

- V1 should expose the inferred plan clearly enough that developers can inspect
  and override it
- this is an ergonomics and safety feature, not a replacement for ORM judgment
