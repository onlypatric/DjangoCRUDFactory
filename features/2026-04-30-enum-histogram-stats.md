# Feature Request: Enum Histogram And Grouped Stats Helpers

## Summary

`CRUDFactory` should support compact helpers for “count this relation by enum
value” response blocks.

This is a natural extension of the existing aggregate stats support.

## Problem

`count_stat(...)` works well, but it becomes verbose when the same enum must be
counted repeatedly across many values:

- `available`
- `preparing`
- `charging`
- `faulted`
- `offline`
- ...

This creates large repetitive DTOs that are structurally obvious but noisy.

## Desired Capability

Support patterns like:

```python
status_summary: ChargepointStatusSummary = enum_count_stat(
    lookup="chargepoints",
    enum=OcppStatusMap,
    filter=visible_chargepoint_filter,
    distinct=True,
)
```

Or:

```python
@enum_summary(enum=OcppStatusMap, lookup="chargepoints", filter=...)
@dataclass(frozen=True)
class ChargepointStatusSummary:
    pass
```

## Required Behavior

- generate one field per enum member or configured subset
- count rows by enum value
- support optional filtering and distinct behavior
- work inside nested response DTOs

## Why This Matters

Status histograms are everywhere in operational products:

- station status overviews
- connector status dashboards
- device fleet health summaries
- alert severity counts

This is exactly the kind of repeated domain boilerplate the library should
compress.

## Suggested Implementation Direction

- build on top of the existing stats infrastructure
- add enum-aware stat spec helpers
- optionally support naming overrides for response field labels

## Test Plan

- enum histogram response block counts all configured enum values correctly
- filters and distinct mode work
- nested response blocks remain serializable
- schema/docs show the generated histogram fields

## Assumptions

- V1 can focus on simple enum-to-count maps, not arbitrary grouped pivots
- explicit enum input is preferable to trying to infer enum semantics from raw
  strings
