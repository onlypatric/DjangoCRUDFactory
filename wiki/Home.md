# CRUDFactory

CRUDFactory is a Django REST Framework library that generates typed CRUD APIs
from Django models and Python dataclasses.

This page is the main documentation page for the library. It is written for
people who may be new to Django, new to DRF, or simply new to this library.

## Index

- [What This Library Does](#what-this-library-does)
- [How To Install It](#how-to-install-it)
- [How To Add It To Django](#how-to-add-it-to-django)
- [The Built-In ACL System](#the-built-in-acl-system)
- [The Core Mental Model](#the-core-mental-model)
- [What A DTO Is](#what-a-dto-is)
- [Why Create Update And Patch Often Need Different DTOs](#why-create-update-and-patch-often-need-different-dtos)
- [The Shortest Working Factory](#the-shortest-working-factory)
- [When The Minimal Style Is Enough](#when-the-minimal-style-is-enough)
- [When You Should Use Explicit Handlers](#when-you-should-use-explicit-handlers)
- [How Request DTO Validation Works](#how-request-dto-validation-works)
- [How Response DTOs Work](#how-response-dtos-work)
- [How Filtering And Ordering Work](#how-filtering-and-ordering-work)
- [How Field Mapping Works](#how-field-mapping-works)
- [How Aggregate Stats Work](#how-aggregate-stats-work)
- [How Custom Actions Work](#how-custom-actions-work)
- [How ACL Integration Works](#how-acl-integration-works)
- [How Pagination Works](#how-pagination-works)
- [How Error Responses Look](#how-error-responses-look)
- [Important CRUDFactory Parameters](#important-crudfactory-parameters)
- [A Complete Example](#a-complete-example)
- [Reference Pages](#reference-pages)

## What This Library Does

CRUDFactory helps you avoid repeating the same DRF code for every resource.

Without a helper like this, a normal CRUD endpoint often needs:

- one serializer for create
- one serializer for update
- one serializer for patch
- one serializer for the response
- one viewset
- manual filter and ordering wiring
- manual response shaping
- optional ACL wiring

CRUDFactory lets you describe most of that through:

- a Django model
- request dataclasses
- a response dataclass or response mapper
- field metadata

It then generates the DRF viewset, router helpers, filtering, ordering,
validation, response rendering, optional ACL checks, and optional custom
actions.

## How To Install It

If this repository is on your machine and you want to use it directly:

```bash
pip install -e .
```

If you want OpenAPI schema support too:

```bash
pip install -e ".[schema]"
```

The `-e` flag means editable install. That is useful during development because
changes in the repository are immediately visible to the Python environment.

If you want the project virtual environment set up for you, use the helper
scripts shipped in the repository.

Unix or macOS:

```bash
bash scripts/setup_venv.sh
```

Windows:

```bat
scripts\setup_venv.bat
```

## How To Add It To Django

CRUDFactory can be used in two broad ways.

### 1. CRUD generation only

If you only want the generated CRUD endpoints and do not want to use the
built-in ACL models or management commands, you can install the package and
import from it in your app code without relying on its Django app models.

### 2. CRUD generation plus the built-in ACL system

If you want to use the built-in ACL backend, Django models, bootstrap helpers,
and management commands, add `crudfactory` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "crudfactory",
]
```

If you also want schema generation through `drf-spectacular`:

```python
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "drf_spectacular",
    "crudfactory",
]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
```

## The Built-In ACL System

CRUDFactory was designed with this ACL model in mind, but ACL is optional.

You can:

- ignore ACL completely
- use the built-in ACL system
- provide your own backend that satisfies the `ACLBackend` protocol

The main settings are:

```python
CRUDFACTORY = {
    "ACL_ENABLED": True,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

Meaning:

- `ACL_ENABLED`
  Enables or disables the built-in Django ACL backend behavior.

- `ACL_AUTO_CREATE_TABLES`
  If `True`, CRUDFactory tries to create missing ACL tables when Django starts.

Recommended production-style setup:

```python
CRUDFACTORY = {
    "ACL_ENABLED": True,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

Then run normal Django migrations:

```bash
python -m django migrate
```

If you do not want ACL at all:

```python
CRUDFACTORY = {
    "ACL_ENABLED": False,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

The automatic table creation feature exists to make local development and quick
prototypes easier. It should be treated as a convenience feature, not as the
default production deployment strategy.

## The Core Mental Model

CRUDFactory expects you to think about an API resource in a few separate parts:

- the Django model that stores the data
- the request DTOs that describe what clients are allowed to send
- the response DTO that describes what clients receive
- optional metadata on DTO fields
- optional ACL rules
- optional custom actions

The key idea is that your API contract should be explicit and typed, even when
the amount of boilerplate is reduced.

## What A DTO Is

`DTO` stands for `Data Transfer Object`.

In this library, a DTO is simply a Python `@dataclass` used as a contract for
API data.

There are two main kinds:

- request DTOs
  These describe incoming request bodies such as create, update, and patch.

- response DTOs
  These describe the JSON shape returned on successful responses.

Why this matters:

- your Django model describes database structure
- your DTO describes API structure

Those two things are often similar, but they are not always the same. You may
want different field names, a narrower public contract, validation rules, or a
response assembled from multiple related models.

## Why Create Update And Patch Often Need Different DTOs

These three actions often have different semantics:

- `create`
  A client is creating a new row. Some fields may be required here.

- `update`
  A client is replacing the full writable state. Required fields are usually
  still required.

- `patch`
  A client is changing only some fields. Most fields are usually optional here.

That is why many APIs use:

- one dataclass for create
- one dataclass for update
- one dataclass for partial update

In simple cases, create and update may look almost identical, while patch is
the nullable version of those fields.

## The Shortest Working Factory

This is the smallest useful configuration:

```python
from dataclasses import dataclass, field

from crudfactory import CRUDFactory, length, range_, regex


@dataclass
class ItemCreateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=80)})
    quantity: int = field(metadata=range_(min=0, max=500))


@dataclass
class ItemUpdateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=80)})
    quantity: int = field(metadata=range_(min=0, max=500))


@dataclass
class ItemPatchDTO:
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=80)},
    )
    quantity: int | None = field(default=None, metadata=range_(min=0, max=500))


factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
)
```

This works because:

- CRUDFactory can generate simple create, update, and patch handlers when you
  do not provide explicit ones
- if you omit `response_mapper` and `response_dataclass`, CRUDFactory can build
  a response mapper automatically from `update_input`

That minimal path is intentionally aimed at low-boilerplate single-model CRUD.

## When The Minimal Style Is Enough

Use the minimal style when:

- one endpoint mostly maps to one Django model
- writes are simple field assignment
- PATCH can ignore `None` values rather than writing SQL `NULL`
- the response contract is close to the model or update DTO contract

This is the “quick CRUD” path the library is best at.

## When You Should Use Explicit Handlers

Use explicit `create_handler`, `update_handler`, and `partial_update_handler`
when:

- one write affects multiple models
- you need service-layer behavior
- PATCH semantics are custom
- write-time business rules are complex
- a nullable model field must truly be set to `NULL` during patch

Use an explicit `response_mapper` when:

- the response combines multiple models
- the response shape differs strongly from the writable fields
- you want complete control over response construction

## How Request DTO Validation Works

Request validation is declared in dataclass field metadata.

The package exports these validation helpers:

- `regex(...)`
- `length(...)`
- `range_(...)`
- `choices(...)`

Example:

```python
from dataclasses import dataclass, field

from crudfactory import choices, length, range_, regex


@dataclass
class ConnectorCreateDTO:
    name: str = field(
        metadata={
            **regex(r"^[A-Za-z0-9 -]+$"),
            **length(min=2, max=80),
        }
    )
    status: str = field(metadata=choices(["online", "offline", "faulted"]))
    power_kw: int = field(metadata=range_(min=0, max=500))
```

CRUDFactory turns those metadata declarations into serializer validation.

## How Response DTOs Work

A response DTO describes successful output.

You can provide responses in two ways:

### 1. Let CRUDFactory derive a simple response automatically

If you do not provide `response_mapper` or `response_dataclass`, CRUDFactory
falls back to the shape of `update_input`.

That is useful for very simple CRUD endpoints.

### 2. Provide a response dataclass or response mapper explicitly

Example:

```python
from dataclasses import dataclass, field

from crudfactory import filterable, model_field, orderable


@dataclass
class ConnectorResponseDTO:
    id: int
    chargepoint_name: str = field(
        metadata={**model_field("chargepoint__name"), **filterable(), **orderable()}
    )
    name: str = field(metadata={**filterable(lookups=("exact", "icontains")), **orderable()})
    status: str = field(metadata=filterable())
```

Then:

```python
factory = CRUDFactory(
    model=Connector,
    create_input=ConnectorCreateDTO,
    update_input=ConnectorUpdateDTO,
    partial_update_input=ConnectorPatchDTO,
    response_dataclass=ConnectorResponseDTO,
)
```

If the response cannot be derived cleanly from metadata alone, provide
`response_mapper`.

## How Filtering And Ordering Work

Filtering and ordering are declared on response DTO fields, not on request
DTOs.

The helpers are:

- `filterable(...)`
- `orderable(...)`

Example:

```python
from dataclasses import dataclass, field

from crudfactory import filterable, orderable


@dataclass
class ItemResponseDTO:
    id: int
    name: str = field(
        metadata={
            **filterable(lookups=("exact", "icontains")),
            **orderable(),
        }
    )
    quantity: int = field(
        metadata={
            **filterable(lookups=("gte", "lte")),
            **orderable(),
        }
    )
```

That allows URLs like:

- `GET /items/?name=widget`
- `GET /items/?name__icontains=wid`
- `GET /items/?quantity__gte=10`
- `GET /items/?ordering=-quantity,name`

If the public field name should map to a different ORM lookup, pass it to the
helper:

```python
supplier_name: str = field(
    metadata={
        **filterable("supplier__name", lookups=("exact", "icontains")),
        **orderable("supplier__name"),
    }
)
```

## How Field Mapping Works

Use `model_field(...)` when the DTO field name differs from the model field
name.

Example:

```python
from dataclasses import dataclass, field

from crudfactory import model_field


@dataclass
class ItemCreateDTO:
    public_name: str = field(metadata=model_field("name"))
```

This means:

- public API field: `public_name`
- Django model field: `name`

`model_field(...)` can also carry read and write transforms:

```python
price: str = field(
    metadata=model_field(
        "price_cents",
        read_transform=lambda cents: f"{cents / 100:.2f}",
        write_transform=lambda euros: int(float(euros) * 100),
    )
)
```

## How Aggregate Stats Work

Aggregate stats are declared on response DTO fields.

The helpers are:

- `count_stat(...)`
- `sum_stat(...)`
- `avg_stat(...)`
- `min_stat(...)`
- `max_stat(...)`

Example:

```python
from dataclasses import dataclass, field

from django.db.models import Q
from crudfactory import count_stat


@dataclass
class ChargerStatsDTO:
    online: int = count_stat("connectors", filter=Q(connectors__status="online"))
    offline: int = count_stat("connectors", filter=Q(connectors__status="offline"))


@dataclass
class LocationResponseDTO:
    id: int
    name: str
    stats: ChargerStatsDTO = field(default_factory=ChargerStatsDTO)
```

CRUDFactory discovers those stat fields, annotates the queryset, and injects
the aggregate values into the response DTO.

## How Custom Actions Work

Custom actions are extra endpoints attached to the generated viewset.

There are two helpers:

- `detail_action(...)`
  For routes like `POST /items/{id}/activate/`

- `collection_action(...)`
  For routes like `POST /items/bulk-import/`

Example detail action:

```python
from dataclasses import dataclass

from crudfactory import detail_action


@dataclass
class ActivateInputDTO:
    reason: str | None = None


@dataclass
class ActivateResponseDTO:
    ok: bool


activate_action = detail_action(
    name="activate",
    input_dataclass=ActivateInputDTO,
    response_dataclass=ActivateResponseDTO,
    handler=activate_item,
)
```

Pass these through the factory’s `custom_actions` parameter.

## How ACL Integration Works

ACL integration is configured through:

- `ACLBackend`
- `ACLConfig`
- `ACLActionConfig`
- `crud_acl(...)`

The fastest path is `crud_acl(...)`:

```python
from crudfactory import DjangoACLBackend, crud_acl


factory = CRUDFactory(
    model=Connector,
    create_input=ConnectorCreateDTO,
    update_input=ConnectorUpdateDTO,
    partial_update_input=ConnectorPatchDTO,
    acl=crud_acl(
        backend=DjangoACLBackend(),
        permission_prefix="app.connector",
        resource_ref_from_instance=connector_resource_ref,
        resource_ref_from_create_input=create_resource_ref,
        resource_ref_from_update_input=update_resource_ref,
        resource_ref_from_patch_input=patch_resource_ref,
    ),
)
```

`crud_acl(...)` uses the default permission mapping:

- `list` -> `{prefix}.read`
- `retrieve` -> `{prefix}.read`
- `create` -> `{prefix}.create`
- `update` -> `{prefix}.update`
- `partial_update` -> `{prefix}.update`
- `destroy` -> `{prefix}.delete`

If you need different behavior, build an `ACLConfig` explicitly.

## How Pagination Works

You can pass a normal DRF pagination class to `pagination_class`.

If you want a compact helper for the common page-number style, use
`page_number_pagination(...)`:

```python
from crudfactory import CRUDFactory, page_number_pagination


factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
    pagination_class=page_number_pagination(page_size=25),
)
```

## How Error Responses Look

Successful responses use your response DTO contract.

Unsuccessful responses follow DRF-style error payloads.

### Validation errors

Status: `400`

Typical shape:

```json
{
  "name": ["Ensure this field has at least 2 characters."]
}
```

### Not found

Status: `404`

Typical shape:

```json
{
  "detail": "Not found."
}
```

When ACL is configured with `unauthorized_as_404=True`, unauthorized access to
single resources may also appear as `404`.

### Forbidden

Status: `403`

Typical shape:

```json
{
  "detail": "You do not have permission to perform this action."
}
```

### Method not allowed

Status: `405`

Typical shape:

```json
{
  "detail": "Method \"POST\" not allowed."
}
```

## Important CRUDFactory Parameters

The most important `CRUDFactory(...)` parameters are:

- `model`
  The Django model behind the resource.

- `create_input`, `update_input`, `partial_update_input`
  Request DTO dataclasses for `POST`, `PUT`, and `PATCH`.

- `response_mapper`
  Explicit callable that turns one model instance into one response DTO.

- `response_dataclass`
  Response DTO type used when CRUDFactory can build the mapper automatically.

- `create_handler`, `update_handler`, `partial_update_handler`
  Explicit write hooks. Use these when the write path is not a simple
  single-model assignment.

- `writable_fields`
  Optional allowlist of DTO field names for automatic writes. If omitted,
  CRUDFactory uses all fields in the relevant request DTO.

- `custom_actions`
  Typed extra routes produced through `detail_action(...)` or
  `collection_action(...)`.

- `acl`
  Optional ACL integration configuration.

- `queryset`
  Custom queryset used by the generated viewset.

- `lookup_field`, `lookup_url_kwarg`
  Standard DRF lookup configuration.

- `permission_classes`, `authentication_classes`
  Standard DRF security hooks.

- `pagination_class`
  DRF pagination class or one from `page_number_pagination(...)`.

- `app_name`, `route`, `basename`
  Routing and namespacing controls.

## A Complete Example

```python
from dataclasses import dataclass, field

from crudfactory import (
    CRUDFactory,
    filterable,
    length,
    model_field,
    orderable,
    range_,
    regex,
)


@dataclass
class ItemCreateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=80)})
    quantity: int = field(metadata=range_(min=0, max=500))


@dataclass
class ItemUpdateDTO:
    name: str = field(metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=80)})
    quantity: int = field(metadata=range_(min=0, max=500))


@dataclass
class ItemPatchDTO:
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[A-Za-z ]+$"), **length(min=2, max=80)},
    )
    quantity: int | None = field(default=None, metadata=range_(min=0, max=500))


@dataclass
class ItemResponseDTO:
    id: int
    public_name: str = field(
        metadata={
            **model_field("name"),
            **filterable(lookups=("exact", "icontains")),
            **orderable(),
        }
    )
    quantity: int = field(
        metadata={
            **filterable(lookups=("gte", "lte")),
            **orderable(),
        }
    )


factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
    response_dataclass=ItemResponseDTO,
)
```

This one factory gives you:

- `GET /items/`
- `GET /items/{pk}/`
- `POST /items/`
- `PUT /items/{pk}/`
- `PATCH /items/{pk}/`
- `DELETE /items/{pk}/`

with typed validation, filtering, ordering, and the declared response shape.

## Reference Pages

Main references:

- [CRUDFactory](CRUDFactory.md)
- [Validation Helpers](Validation-Helpers.md)
- [Filtering And Ordering](Filtering-And-Ordering.md)
- [model_field](model_field.md)
- [Aggregate Stats](Aggregate-Stats.md)
- [Custom Actions](Custom-Actions.md)
- [page_number_pagination](page_number_pagination.md)
- [crud_acl](crud_acl.md)

ACL references:

- [ACLBackend](ACLBackend.md)
- [ACLActionConfig](ACLActionConfig.md)
- [ACLConfig](ACLConfig.md)
- [ACLResourceRef](ACLResourceRef.md)
- [DjangoACLBackend](DjangoACLBackend.md)
- [DjangoACLService](DjangoACLService.md)
- [ACLBootstrapper](ACLBootstrapper.md)
- [ACLPermissionSeed](ACLPermissionSeed.md)
- [ACLGroupSeed](ACLGroupSeed.md)
- [ACLResourceSeed](ACLResourceSeed.md)
