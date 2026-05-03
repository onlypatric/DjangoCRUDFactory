# Feature Request: Nested Subresource Endpoints

## Summary

`CRUDFactory` should support generated **subresource endpoints** like:

- `/locations/{location_id}/chargepoints/`
- `/chargepoints/{chargepoint_id}/connectors/`
- `/stations/{station_id}/hosts/{host_id}/items/`

with parent scoping, typed request/response contracts, filtering, ordering, and
ACL applied in the context of the parent resource.

## Problem

Right now a factory can expose one resource collection cleanly, but many real
APIs are organized by parent-child routes rather than only top-level routes.

Teams often want:

- child listing under a specific parent
- child create automatically tied to the parent in the URL
- child update and delete still constrained by that parent
- optional top-level and nested variants for the same model

That currently pushes people into:

- custom routers
- custom queryset scoping logic
- custom create handlers just to bind the parent FK

## Desired Capability

A child factory should be able to say:

```python
connector_factory = CRUDFactory(
    model=Connector,
    ...,
    parent_resource=parent_scope(
        parent_model=Chargepoint,
        parent_lookup_field="chargepoint_id",
        relation_name="connectors",
    ),
)
```

Then the generated endpoints would behave as nested resources.

## Public API Direction

Possible helper:

```python
parent_scope(
    *,
    parent_model: type[models.Model],
    parent_lookup_url_kwarg: str = "parent_pk",
    child_fk_field: str | None = None,
    relation_name: str | None = None,
    bind_on_create: bool = True,
)
```

Or more router-oriented:

```python
factory.get_nested_urlpatterns(
    prefix="locations/<int:location_id>/chargepoints",
    parent_resolver=...,
)
```

## Required Behavior

- list only child rows under the parent
- create child rows bound to the parent from the URL
- reject or ignore conflicting parent IDs in the body
- update/delete only when the child belongs to that parent
- support ACL on both:
  - parent scope
  - child resources

## Why This Matters

Nested resources are everywhere:

- sites -> chargepoints
- chargepoints -> connectors
- organizations -> users
- orders -> line items
- forms -> questions

If CRUDFactory cannot generate these cleanly, teams still need a large amount
of custom view and routing code.

## V1 Scope

Start with:

- one parent level
- parent-child FK relations
- nested list/create/detail/update/delete
- parent binding on create
- child queryset scoping on every action

V1 does not need:

- unlimited nested router trees
- non-FK inferred graph traversal
- arbitrary custom URL topologies

## Suggested Implementation Direction

- add a parent-scope config object
- resolve parent instance early in the viewset flow
- scope `get_queryset()` by parent
- inject parent FK during create
- ensure detail lookups cannot escape the parent scope

## Test Plan

- nested list returns only parent children
- nested create binds the parent automatically
- nested detail rejects a child from a different parent
- nested update/delete remain parent-scoped
- filters and ordering still work inside the nested route
- schema/docs show nested URL parameters clearly

## Assumptions

- top-level and nested factories may coexist for the same model
- V1 should prioritize FK-based child resources because that covers most cases
