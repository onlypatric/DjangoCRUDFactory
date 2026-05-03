# Feature Request: Metadata Composition Helpers

## Summary

`CRUDFactory` should offer small helpers that make field metadata composition
less noisy in DTO declarations.

This is mostly a developer-experience improvement, but it becomes important once
DTO files grow large.

## Problem

A very common pattern is:

```python
field(
    metadata={
        **model_field(...),
        **filterable(...),
        **orderable(),
    }
)
```

This is not hard to understand, but it is repetitive and syntactically noisy.

## Desired Capability

Simple helper:

```python
metadata=compose_meta(
    model_field("status", read_transform=normalize_status),
    filterable(lookups=("exact",)),
    orderable(),
)
```

Or a more opinionated helper:

```python
metadata=field_config(
    source="status",
    read_transform=normalize_status,
    filterable=("exact",),
    orderable=True,
)
```

## Required Behavior

- merge metadata fragments predictably
- preserve existing helper semantics
- support both request and response field metadata use cases

## Why This Matters

This helps with:

- readability
- autocomplete-oriented API discovery
- reducing syntax noise for new users

It will not remove whole views, but it does make the “describe everything in the
factory” style much more approachable.

## Suggested Implementation Direction

- add a minimal `compose_meta(...)` helper first
- only add a more opinionated `field_config(...)` wrapper if it remains clear
  and not overly magical

## Test Plan

- metadata fragments merge as expected
- overlapping keys fail clearly or follow a documented override rule
- existing helpers remain usable directly without the composition helper

## Assumptions

- this should stay intentionally small
- clarity matters more than building a giant metadata DSL
