# CRUDFactory

CRUDFactory is a Django REST Framework library that generates typed CRUD APIs
from Django models and Python dataclasses.

It is built for this kind of setup:

```python
factory = CRUDFactory(
    model=InventoryItem,
    write_input=ItemWriteFields,
)
```

From that one declaration, CRUDFactory can generate:

- CRUD routes
- request validation
- automatic simple writes
- automatic response DTOs
- filtering and ordering
- nested response shapes
- aggregate stats
- typed custom actions
- OpenAPI schema metadata
- generated Markdown docs
- ACL integration

## Index

- [What This Library Does](#what-this-library-does)
- [Who This Is For](#who-this-is-for)
- [Installation](#installation)
- [The Mental Model](#the-mental-model)
- [The Fastest Working Example](#the-fastest-working-example)
- [The Grouped Metadata API](#the-grouped-metadata-api)
- [Automatic CRUD Modes](#automatic-crud-modes)
- [When To Use Explicit Configuration](#when-to-use-explicit-configuration)
- [Responses And Errors](#responses-and-errors)
- [ACL](#acl)
- [Generated Docs](#generated-docs)
- [Project Layout Recommendation](#project-layout-recommendation)
- [Learning Path](#learning-path)
- [Wiki Pages](#wiki-pages)

## What This Library Does

CRUDFactory reduces the repetitive part of building DRF APIs.

Instead of hand-writing:

- serializers
- viewsets
- list/detail/create/update/patch/delete methods
- field validation glue
- filter and ordering plumbing

you describe the contract using dataclasses and let the library generate the
rest.

It does not replace Django models.

It does not try to hide DRF entirely.

It simply removes the most repetitive API boilerplate while keeping the
contracts explicit and typed.

## Who This Is For

CRUDFactory is useful when:

- you already use Django and DRF
- you want less CRUD boilerplate
- you want typed request and response contracts
- you still want the option to drop to explicit logic for complex resources

It is especially useful when a codebase has many endpoints that are mostly:

- one model
- one response contract
- standard CRUD operations

## Installation

Runtime install:

```bash
pip install -e .
```

If you want OpenAPI schema generation with `drf-spectacular`:

```bash
pip install -e ".[schema]"
```

## The Mental Model

CRUDFactory works like this:

```text
request JSON
  -> generated DRF serializer
  -> request dataclass
  -> generated simple write or explicit handler
  -> Django model instance
  -> generated or explicit response dataclass
  -> response JSON
```

The key idea is:

- request dataclasses define what clients may send
- response dataclasses define what clients receive
- metadata on those dataclass fields defines validation, mapping, filtering, ordering, and stats

## The Fastest Working Example

### 1. Django model

```python
from django.db import models


class InventoryItem(models.Model):
    name = models.CharField(max_length=80)
    quantity = models.IntegerField(default=0)
```

### 2. One dataclass for writable fields

```python
from dataclasses import dataclass, field

from crudfactory import RequestConstraints


@dataclass
class ItemWriteFields:
    name: str = field(
        metadata=RequestConstraints.regex(r"^[A-Za-z0-9 -]+$").length(min=2, max=80)
    )
    quantity: int = field(metadata=RequestConstraints.range(min=0, max=500))
```

### 3. Factory declaration

```python
from crudfactory import CRUDFactory


item_factory = CRUDFactory(
    model=InventoryItem,
    write_input=ItemWriteFields,
    route="items",
    basename="item",
    app_name="inventory",
)
```

### 4. Mount in Django `urls.py`

```python
from .api import item_factory

app_name = item_factory.app_name
urlpatterns = item_factory.get_urlpatterns()
```

This gives you:

- `GET /items/`
- `GET /items/{id}/`
- `POST /items/`
- `PUT /items/{id}/`
- `PATCH /items/{id}/`
- `DELETE /items/{id}/`

## The Grouped Metadata API

The recommended style is to use grouped helper classes instead of importing a
long list of standalone helpers.

Use:

- `RequestConstraints`
- `RequestFilter`
- `RequestMapping`
- `ResponseField`
- `ResponseStats`

Example:

```python
from dataclasses import dataclass, field

from crudfactory import RequestConstraints, RequestFilter, RequestMapping


@dataclass
class ItemWriteFields:
    public_name: str = field(
        metadata=RequestMapping.model_field("name")
        .regex(r"^[A-Za-z0-9 -]+$")
        .length(min=2, max=80)
    )
    quantity: int = field(metadata=RequestConstraints.range(min=0, max=500))


@dataclass
class ItemResponseDTO:
    id: int
    public_name: str = field(
        metadata=RequestMapping.model_field("name")
        .filterable(lookups=("exact", "icontains"))
        .orderable()
    )
    quantity: int = field(metadata=RequestFilter.filterable().orderable())
```

This style is better for autocomplete and keeps imports readable.

## Automatic CRUD Modes

CRUDFactory supports several levels of automation.

### Minimal mode

```python
factory = CRUDFactory(
    model=InventoryItem,
    write_input=ItemWriteFields,
)
```

This derives:

- create input
- update input
- patch input
- generated simple write handlers
- generated response DTO

### Create-only plus writable fields

```python
factory = CRUDFactory(
    model=Chargepoint,
    create_only_input=ChargepointCreateOnlyFields,
    write_input=ChargepointMutableFields,
)
```

This is useful when create accepts fields that update should not expose.

### Explicit response contract

```python
factory = CRUDFactory(
    model=Connector,
    write_input=ConnectorWriteFields,
    response_dataclass=ConnectorResponseDTO,
)
```

Use this when the response shape differs from the writable fields.

## When To Use Explicit Configuration

Stay in minimal mode when:

- one endpoint maps cleanly to one model
- the API field names match the model field names
- the response can be derived from the same fields
- the write only touches one model

Move to explicit config when:

- create requires different fields than update
- response shape differs from request shape
- response includes related models
- response includes child collections
- response includes aggregate stats
- writes touch multiple models
- ACL or custom actions are involved

## Responses And Errors

Successful responses use your response DTO shape.

Error responses do not.

They use normal DRF-style error payloads.

### Validation error example

```json
{
  "name": ["Ensure this field has at least 2 characters."]
}
```

### Not found example

```json
{
  "detail": "Not found."
}
```

This matters for frontend work:

- success payloads are DTO-shaped
- error payloads are DRF-shaped

## ACL

CRUDFactory supports ACL integration through `crud_acl(...)` and the Django
ACL backend shipped in this repository.

Typical pattern:

```python
from crudfactory import ACLResourceRef, DjangoACLBackend, crud_acl


connector_acl = crud_acl(
    backend=DjangoACLBackend(),
    permission_prefix="app.connector",
    resource_ref_from_instance=lambda connector: ACLResourceRef(
        "connector",
        f"{connector.chargepoint.serial_number}/{connector.name}",
    ),
)
```

Use ACL when:

- list responses must be filtered by access
- detail routes must enforce resource-level visibility
- custom actions must require resource-specific permissions

## Generated Docs

CRUDFactory can expose documentation in two ways:

### OpenAPI schema

If `drf-spectacular` is installed and configured.

### Markdown

Each factory can render Markdown docs from its own contract:

```python
markdown = factory.render_markdown_docs(
    title="Connector CRUD Factory",
    base_path="/api",
)
```

The demo Django app also serves generated factory docs directly.

## Project Layout Recommendation

The cleanest structure is one file per factory.

Recommended pattern:

```text
your_app/
  models.py
  urls.py
  factories/
    location_factory.py
    chargepoint_factory.py
    connector_factory.py
```

Each factory file should contain:

- its request dataclasses
- its response dataclasses
- its queryset plan
- its ACL and custom action wiring
- the `CRUDFactory(...)` declaration

This keeps resources easy to move and easy to read.

## Learning Path

If you are new to this library, learn it in this order:

1. build one simple CRUD resource with `write_input`
2. add `RequestConstraints`
3. add `RequestFilter`
4. add `ResponseField`
5. add `ResponseStats`
6. add custom actions
7. add ACL

## Wiki Pages

This repository now includes a `wiki/` folder with GitHub-friendly pages:

- [Home](wiki/Home.md)
- [CRUDFactory](wiki/CRUDFactory.md)
- [ACLBackend](wiki/ACLBackend.md)
- [ACLActionConfig](wiki/ACLActionConfig.md)
- [ACLConfig](wiki/ACLConfig.md)
- [ACLResourceRef](wiki/ACLResourceRef.md)
- [DjangoACLBackend](wiki/DjangoACLBackend.md)
- [DjangoACLService](wiki/DjangoACLService.md)

The wiki is now the main docs surface. Start with [Home](wiki/Home.md), then
use the per-class pages when you need exact reference details.
