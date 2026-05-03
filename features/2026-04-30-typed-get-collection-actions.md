# Feature Request: Typed GET Collection Actions With Query DTOs

## Summary

`CRUDFactory` should support non-grouped, typed, read-only collection actions
driven by `request.query_params` rather than request bodies.

This is different from grouped collection actions:

- grouped actions reduce many source rows into one grouped response
- typed GET collection actions may still return flat, computed, filtered, or
  otherwise custom-shaped collection responses

## Problem

The current custom action model is strongest for:

- `POST` actions
- request body DTOs
- detail actions
- collection actions that are mutation-oriented or body-driven

But many real read endpoints are:

- `GET`
- collection-scoped
- query-param driven
- computed or filtered beyond a normal CRUD list

Those still tend to fall back to ad-hoc APIViews.

## Desired Capability

Allow collection actions like:

```python
collection_action(
    name="station_summary",
    methods=("get",),
    query_dataclass=StationSummaryQuery,
    response_dataclass=StationSummaryResponse,
    handler=build_station_summary,
)
```

Where:

- `query_dataclass` is validated from `request.query_params`
- `handler` returns a typed response DTO
- the action is mounted as a normal DRF extra action

## Required Behavior

- validation from query params, not request body
- typed query DTO support
- typed response DTO support
- schema/docs expose query parameters correctly
- optional ACL support for the action itself

## Why This Matters

This covers a large class of non-mutating read endpoints:

- dashboards
- summaries
- custom reports
- filtered computed reads
- export-style endpoints that are not plain CRUD lists

Without this, teams still build custom GET views for things the factory could
reasonably own.

## Relationship To Other Requests

- `30-april-2026.md` covers grouped GET collection actions with source-row ACL.
- this request is broader and less specialized: it covers typed GET collection
  actions even when the response is not a grouped reduction.
- `2026-04-30-advanced-query-dtos.md` is related but focused on normal list
  endpoints rather than extra actions.

## Suggested Implementation Direction

- extend collection action config with `query_dataclass`
- parse and validate from `request.query_params`
- keep `input_dataclass` for body-driven actions unchanged
- allow action methods including `GET`

## Test Plan

- GET collection action validates query params into a DTO
- request body is ignored for GET query actions
- response DTO is serialized correctly
- schema/docs expose query params, not request body
- existing POST collection actions remain unchanged

## Assumptions

- V1 does not need to replace grouped collection actions
- V1 should keep GET query actions explicit rather than inferring them from
  `methods=("get",)` alone
