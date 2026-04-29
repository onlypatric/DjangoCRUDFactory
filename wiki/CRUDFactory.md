# CRUDFactory

`CRUDFactory` is the main class of the library.

It generates Django REST Framework CRUD endpoints from:

- a Django model
- request dataclass types
- a response mapper or response dataclass
- optional ACL, pagination, and custom action configuration

## What It Does

A `CRUDFactory` instance can generate:

- a DRF `ModelViewSet`
- a DRF router
- Django URL patterns
- response mapping helpers
- Markdown docs for the factory

## Constructor Shape

Typical usage:

```python
factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
    response_mapper=to_item_response,
    route="items",
    basename="item",
    app_name="inventory",
)
```

## Most Important Parameters

### `model`

The Django model that backs the resource.

### `create_input`, `update_input`, `partial_update_input`

Dataclass types that describe the request body for:

- `POST`
- `PUT`
- `PATCH`

### `response_mapper`

A callable that takes a model instance and returns a response dataclass
instance.

### `response_dataclass`

An alternative to `response_mapper` when the library can auto-build the mapper
from the response type declaration.

### `create_handler`, `update_handler`, `partial_update_handler`

Optional explicit persistence hooks.

Use these when writes are more complex than assigning model fields directly.

### `writable_fields`

Allowlist of DTO field names that may be written automatically by the built-in
simple-write path.

### `custom_actions`

Typed extra endpoints, such as:

- `POST /items/{id}/activate/`
- `POST /items/bulk-import/`

### `acl`

Factory-level ACL configuration.

### `queryset`

Custom base queryset for list and detail views.

### `pagination_class`

DRF pagination class, including one produced by `page_number_pagination(...)`.

## What It Generates

In normal full-CRUD mode:

- `GET /route/`
- `GET /route/{id}/`
- `POST /route/`
- `PUT /route/{id}/`
- `PATCH /route/{id}/`
- `DELETE /route/{id}/`

## Main Methods

### `get_viewset_class()`

Returns the generated DRF `ModelViewSet` class.

### `get_router()`

Returns a DRF router with the viewset already registered.

### `get_urlpatterns()`

Returns Django `urlpatterns` for easy use inside an app `urls.py`.

### `get_app_urlconf()`

Returns an include-ready tuple for Django URL mounting.

### `to_dataclass(instance)`

Maps one model instance into the response dataclass.

### `to_response_data(instance)`

Maps one model instance into JSON-ready response data.

### `render_markdown_docs(...)`

Generates a Markdown description of the factory’s API contract.

## Read-Only Mode

Use `CRUDFactory.read_only(...)` when you want:

- list
- retrieve

without write endpoints.

This is useful for:

- summary endpoints
- dashboards
- reporting APIs

## When To Use Automatic Writes

Automatic writes are good when:

- the DTO fields map directly to one Django model
- the write logic is simple field assignment
- there is no multi-model coordination

## When To Use Explicit Handlers

Use explicit handlers when:

- create/update/patch touches related models
- the write triggers service-layer logic
- patch semantics are custom
- write-time business rules are significant

## Minimal Example

```python
factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
)
```

## Related Classes

- [ACLConfig](ACLConfig.md)
- [ACLActionConfig](ACLActionConfig.md)
- [ACLBackend](ACLBackend.md)
