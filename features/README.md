# CRUDFactory Feature Backlog

This folder contains implementation-grade feature requests for the next wave of
`CRUDFactory` capabilities.

The goal is not to add novelty for its own sake. The goal is to remove the
remaining reasons why a Django team would still need to hand-write views for
non-auth flows.

## Progress Summary

- Total tracked feature requests: `15`
- Implemented so far: `15`
- Still planned: `0`

Implemented so far:

1. grouped collection responses with source-row ACL
2. nested related writes
3. bulk typed operations
4. declarative annotation / subquery fields
5. generated field subresource endpoints
6. typed GET collection actions with query DTOs
7. latest related row helpers
8. nested subresource endpoints
9. declarative filtered related collections and prefetch specs
10. enum histogram and grouped stats helpers
11. built-in ACL presets
12. advanced query DTOs for normal list endpoints
13. soft delete and restore lifecycles
14. metadata composition helpers
15. queryset plans derived from response contracts

## Status Overview

| Feature | File | Status | Notes |
| --- | --- | --- | --- |
| Grouped collection responses with source-row ACL | `30-april-2026.md` | `implemented` | Implemented in the library as grouped read-only collection actions with per-row source ACL. |
| Nested related writes | `2026-04-30-nested-related-writes.md` | `implemented` | V1 one-to-many nested collections with transactional create/update/patch reconciliation. |
| Bulk typed operations | `2026-04-30-bulk-operations.md` | `implemented` | Generated bulk create, update, patch, and delete endpoints with structured results and transaction modes. |
| Nested subresource endpoints | `2026-04-30-subresource-endpoints.md` | `implemented` | Parent-scoped factories can now generate nested CRUD routes with queryset scoping, URL-bound parent FK injection, and nested Markdown docs. |
| Latest related row helpers | `2026-04-30-latest-related-values.md` | `implemented` | `latest_related_value(...)` now provides a first-class wrapper for the common latest-child-row scalar pattern. |
| Declarative annotation / subquery fields | `2026-04-30-declarative-annotation-fields.md` | `implemented` | Response DTO fields can now declare `Subquery`, `Exists`, `Case`, and similar queryset annotations directly. |
| Generated field subresource endpoints | `2026-04-30-field-subresource-endpoints.md` | `implemented` | Direct `GET`/`PATCH` field endpoints for concrete model fields, including JSON merge mode and field-specific ACL. |
| Typed GET collection actions with query DTOs | `2026-04-30-typed-get-collection-actions.md` | `implemented` | `collection_action(...)` now supports query-param DTO validation for collection-scoped GET endpoints. |
| Advanced query DTOs for normal list endpoints | `2026-04-30-advanced-query-dtos.md` | `implemented` | `list_query=...` plus `query_search(...)`, `query_range(...)`, `query_list(...)`, `query_exclude(...)`, and `query_ordering(...)` now give normal list endpoints a typed query DTO path. |
| Declarative filtered related collections / prefetch specs | `2026-04-30-filtered-related-collections.md` | `implemented` | `related_list(...)` now lets nested response DTO fields declare their own filtered queryset and recursive prefetch plan. |
| Enum histogram / grouped stats helpers | `2026-04-30-enum-histogram-stats.md` | `implemented` | `enum_summary(...)` now generates count-stat response blocks from enum values while staying inside the normal stats pipeline. |
| Built-in scoped ACL presets | `2026-04-30-built-in-acl-presets.md` | `implemented` | `scoped_read_acl(...)`, `scoped_read_write_acl(...)`, `global_read_acl(...)`, and `global_read_write_acl(...)` now cover the common permission shapes without hand-built `ACLConfig(...)` blocks. |
| Soft delete / restore lifecycles | `2026-04-30-soft-delete-and-restore.md` | `implemented` | `lifecycle=...` now lets `DELETE` archive rows, hide archived records by default, optionally expose `include_archived`, and generate a restore action. |
| Metadata composition helpers | `2026-04-30-metadata-composition-helpers.md` | `implemented` | `compose_meta(...)` now merges metadata fragments predictably and fails fast on duplicate keys, making larger DTOs easier to read. |
| Queryset plans from response contracts | `2026-04-30-queryset-plans-from-response-contracts.md` | `implemented` | `derive_query_plan(...)`, `auto_query_plan()`, and `QueryPlan` now expose inferred `select_related(...)` and `prefetch_related(...)` plans from response contracts, with manual override support. |

## Recommended Order

Every tracked feature request in this backlog is now implemented.

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
