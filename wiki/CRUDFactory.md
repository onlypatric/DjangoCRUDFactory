# CRUDFactory

`CRUDFactory` is the main class of the library.

It generates Django REST Framework endpoints from:

- one Django model
- request DTO dataclasses
- a response mapper or response dataclass
- optional custom actions
- optional ACL configuration
- optional pagination and routing settings

## Main Job

A `CRUDFactory` instance can generate:

- a DRF `ModelViewSet`
- a DRF router
- Django URL patterns
- include-ready URL config tuples
- response DTO instances
- response JSON-like dictionaries
- Markdown docs for the generated API contract

## Constructor Shape

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

## Constructor Parameters

### `model`

The Django model behind the resource.

### `response_mapper`

Callable used to turn one model instance into one response DTO instance.

Use this when the response shape is complex or assembled from multiple models.

### `response_dataclass`

Alternative to `response_mapper`.

If you provide `response_dataclass`, CRUDFactory will try to build the response
mapper automatically from that type declaration.

### `create_input`, `update_input`, `partial_update_input`

Request DTO dataclasses for:

- `POST`
- `PUT`
- `PATCH`

### `create_handler`, `update_handler`, `partial_update_handler`

Optional explicit write hooks.

If you do not provide them and the endpoint is not read-only, CRUDFactory tries
to generate simple write handlers automatically from the request DTO fields.

### `writable_fields`

Optional allowlist of DTO field names that automatic writes may touch.

If omitted, CRUDFactory uses all fields from the relevant request DTO.

### `custom_actions`

Sequence of custom action specs built through:

- `detail_action(...)`
- `collection_action(...)`

### `acl`

Optional factory-level ACL configuration.

### `read_only`

Internal flag used by `CRUDFactory.read_only(...)`. In normal application code,
prefer using the classmethod rather than setting this manually.

### `app_name`

App name used by URL helpers. Defaults to the Django app label.

### `route`

Router path segment. Defaults to the model name.

### `basename`

DRF router basename. Defaults to the model name.

### `queryset`

Optional custom base queryset for list and detail operations.

### `lookup_field`, `lookup_url_kwarg`

Standard DRF lookup configuration.

### `permission_classes`, `authentication_classes`

Standard DRF viewset security configuration.

### `pagination_class`

Optional DRF pagination class, including one created by
`page_number_pagination(...)`.

## Automatic Behavior

CRUDFactory resolves responses in this order:

1. use `response_mapper` if provided
2. otherwise use `response_dataclass` if provided
3. otherwise derive a simple response mapper from `update_input`

CRUDFactory resolves writes like this:

1. use explicit handlers if provided
2. otherwise generate simple handlers from the request DTO fields

That is why this minimal factory works:

```python
factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
)
```

## Generated CRUD Routes

In normal full CRUD mode, the generated viewset exposes:

- `GET /route/`
- `GET /route/{id}/`
- `POST /route/`
- `PUT /route/{id}/`
- `PATCH /route/{id}/`
- `DELETE /route/{id}/`

Plus any configured custom actions.

## Main Methods

### `get_viewset_class()`

Returns the generated DRF `ModelViewSet` subclass.

### `get_router(...)`

Returns a DRF router with the generated viewset already registered.

### `get_urlpatterns(...)`

Returns Django `urlpatterns` suitable for an app-level `urls.py`.

### `get_app_urlconf(...)`

Returns an include-ready tuple:

```python
(urlpatterns, app_name, namespace)
```

### `to_dataclass(instance)`

Maps one model instance into the configured response DTO.

### `to_response_data(instance)`

Maps one model instance into JSON-ready response data, including aggregate stat
injection when stats are declared.

### `render_markdown_docs(...)`

Generates a Markdown description of the factory contract.

## `CRUDFactory.read_only(...)`

Use `CRUDFactory.read_only(...)` when the resource should only expose:

- list
- retrieve

Example:

```python
factory = CRUDFactory.read_only(
    model=InventoryItem,
    response_dataclass=ItemResponseDTO,
)
```

This is useful for:

- dashboards
- reporting endpoints
- summary APIs
- read-only admin resources

## When Automatic Writes Are Good

Automatic writes are a good fit when:

- one endpoint writes to one model
- field assignment is straightforward
- DTO field names mostly match model field names
- patch can ignore `None` values

## When Explicit Handlers Are Better

Use explicit handlers when:

- writes span multiple models
- service-layer orchestration is needed
- patch semantics are custom
- write-time validation is business-specific
- you need complete control over persistence behavior

## Related Pages

- [Home](Home.md)
- [Validation Helpers](Validation-Helpers.md)
- [Filtering And Ordering](Filtering-And-Ordering.md)
- [model_field](model_field.md)
- [Aggregate Stats](Aggregate-Stats.md)
- [Custom Actions](Custom-Actions.md)
- [crud_acl](crud_acl.md)
