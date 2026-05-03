# CRUDFactory Feature Backlog

This folder contains implementation-grade feature requests for the next wave of
`CRUDFactory` capabilities.

The goal is not to add novelty for its own sake. The goal is to remove the
remaining reasons why a Django team would still need to hand-write views for
non-auth flows.

## Status Overview

| Feature | File | Status | Notes |
| --- | --- | --- | --- |
| Grouped collection responses with source-row ACL | `30-april-2026.md` | `implemented` | Implemented in the library as grouped read-only collection actions with per-row source ACL. |
| Nested related writes | `2026-04-30-nested-related-writes.md` | `implemented` | V1 one-to-many nested collections with transactional create/update/patch reconciliation. |
| Bulk typed operations | `2026-04-30-bulk-operations.md` | `planned` | High-value for admin and operational flows. |
| Nested subresource endpoints | `2026-04-30-subresource-endpoints.md` | `planned` | Needed for parent-scoped APIs. |
| Latest related row helpers | `2026-04-30-latest-related-values.md` | `planned` | Specialized version of declarative subquery fields. |
| Declarative annotation / subquery fields | `2026-04-30-declarative-annotation-fields.md` | `implemented` | Response DTO fields can now declare `Subquery`, `Exists`, `Case`, and similar queryset annotations directly. |
| Generated field subresource endpoints | `2026-04-30-field-subresource-endpoints.md` | `implemented` | Direct `GET`/`PATCH` field endpoints for concrete model fields, including JSON merge mode and field-specific ACL. |
| Typed GET collection actions with query DTOs | `2026-04-30-typed-get-collection-actions.md` | `implemented` | `collection_action(...)` now supports query-param DTO validation for collection-scoped GET endpoints. |
| Advanced query DTOs for normal list endpoints | `2026-04-30-advanced-query-dtos.md` | `planned` | Richer collection querying without custom views. |
| Declarative filtered related collections / prefetch specs | `2026-04-30-filtered-related-collections.md` | `planned` | Keeps nested response loading closer to the DTO contract. |
| Enum histogram / grouped stats helpers | `2026-04-30-enum-histogram-stats.md` | `planned` | Reduces repetitive status count DTOs. |
| Built-in scoped ACL presets | `2026-04-30-built-in-acl-presets.md` | `planned` | Cuts repetitive ACL helper glue. |
| Metadata composition helpers | `2026-04-30-metadata-composition-helpers.md` | `planned` | Improves DTO readability and reduces syntax noise. |
| Soft delete / restore lifecycles | `2026-04-30-soft-delete-and-restore.md` | `planned` | Common product lifecycle requirement. |
| Queryset plans from response contracts | `2026-04-30-queryset-plans-from-response-contracts.md` | `planned` | Ergonomics and N+1 safety improvement. |

## Recommended Order

1. `2026-04-30-bulk-operations.md`
   Reason: high-value in admin panels, dashboards, imports, and operational
   tooling.
2. `2026-04-30-subresource-endpoints.md`
   Reason: parent-child APIs are extremely common and still push developers
   toward hand-written viewsets.
3. `2026-04-30-latest-related-values.md`
   Reason: very common pattern, but best implemented after the broader
   annotation/subquery field model exists.
4. `2026-04-30-filtered-related-collections.md`
   Reason: nested read contracts are already strong; this makes them less
   boilerplate-heavy.
5. `2026-04-30-enum-histogram-stats.md`
   Reason: strong productivity win in monitoring/status APIs.
6. `2026-04-30-built-in-acl-presets.md`
    Reason: good readability improvement once the bigger behavioral features are
    in place.
7. `2026-04-30-advanced-query-dtos.md`
    Reason: once CRUD and computed reads are covered, richer query forms become
    the next pressure point.
8. `2026-04-30-soft-delete-and-restore.md`
    Reason: important product requirement, but less foundational than nested
    writes and computed read support.
9. `2026-04-30-queryset-plans-from-response-contracts.md`
    Reason: improves ergonomics and performance, but is safer after more of the
    response-side abstractions are settled.
10. `2026-04-30-metadata-composition-helpers.md`
    Reason: useful DX cleanup, but not a capability blocker.

## Relationship Notes

- `30-april-2026.md` is already implemented. It should not be rewritten as a
  future request again unless the scope changes materially.
- `2026-04-30-latest-related-values.md` is a focused, high-value specialization
  of `2026-04-30-declarative-annotation-fields.md`.
- `2026-04-30-typed-get-collection-actions.md` is related to grouped GET
  actions, but broader: it covers computed collection reads that may still be
  flat or otherwise non-grouped.
- `2026-04-30-filtered-related-collections.md` complements
  `2026-04-30-queryset-plans-from-response-contracts.md`; the former is about
  explicit nested loading declarations, the latter about inference/assistance.

## Selection Criteria

These feature requests were chosen because they:

- remove real reasons to leave `CRUDFactory`
- map cleanly onto common Django backend work
- fit the library's typed dataclass + factory architecture
- can be implemented incrementally without rewriting the whole library
