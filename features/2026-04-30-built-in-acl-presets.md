# Feature Request: Built-In Scoped ACL Presets

## Summary

`CRUDFactory` should ship small, readable ACL preset helpers for the most common
permission shapes.

This is a DX feature, but it matters because ACL configuration appears in many
factory modules and gets repetitive quickly.

## Problem

Even when the underlying ACL integration is sound, app code still ends up
writing repeated wrappers for patterns like:

- scoped read-only
- scoped read/write
- global read-only
- global read/write

That repetition is not dangerous logic, but it is noisy and distracts from the
actual resource contract.

## Desired Capability

Examples:

```python
scoped_read_acl(
    permission="app.ocpp.station.read",
    resource_ref_from_instance=station_resource_ref,
)
```

```python
scoped_read_write_acl(
    read_permission="app.ocpp.station.read",
    update_permission="app.ocpp.station.display.update",
    resource_ref_from_instance=station_resource_ref,
)
```

And global variants:

```python
global_read_acl(...)
global_read_write_acl(...)
```

## Required Behavior

- generate normal `ACLConfig` objects
- express common patterns tersely
- preserve escape hatches for explicit full config

## Why This Matters

This improves:

- readability of factory modules
- consistency across resources
- confidence for teams adopting the ACL layer

It is not a core capability unlock, but it removes a lot of glue code.

## Suggested Implementation Direction

- add a small helpers module layered on top of `crud_acl(...)`
- keep these helpers thin and predictable
- avoid hiding important ACL decisions that should stay explicit

## Test Plan

- helper-generated ACL configs behave like equivalent explicit `crud_acl(...)`
- read-only and read/write presets produce the expected enabled actions
- scoped and global presets behave correctly

## Assumptions

- these helpers should remain convenience wrappers, not a replacement for the
  underlying explicit ACL API
