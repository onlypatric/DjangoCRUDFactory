# CRUDFactory

CRUDFactory is a Django REST Framework library that generates typed CRUD APIs
from Django models and Python dataclasses.

This page is the main reference page for the library. It is written to be
useful even if you have little or no prior experience with Django REST
Framework.

---

## Index

- [What CRUDFactory Is](#what-crudfactory-is)
- [Why This Library Exists](#why-this-library-exists)
- [How To Install The Library](#how-to-install-the-library)
- [How To Configure Django](#how-to-configure-django)
- [How ACL Configuration Works](#how-acl-configuration-works)
- [Core Idea](#core-idea)
- [What A Type Is In CRUDFactory](#what-a-type-is-in-crudfactory)
- [Why There Are Different Types For Create Update And Patch](#why-there-are-different-types-for-create-update-and-patch)
- [The Main Kinds Of Types](#the-main-kinds-of-types)
- [The Shortest Working Setup](#the-shortest-working-setup)
- [The Most Important CRUDFactory Parameters](#the-most-important-crudfactory-parameters)
- [How Automatic CRUD Works](#how-automatic-crud-works)
- [When Minimal Mode Is Enough](#when-minimal-mode-is-enough)
- [When You Need Explicit Types](#when-you-need-explicit-types)
- [The Metadata System](#the-metadata-system)
- [RequestConstraints](#requestconstraints)
- [RequestFilter](#requestfilter)
- [RequestMapping](#requestmapping)
- [ResponseField](#responsefield)
- [ResponseStats](#responsestats)
- [How To Create Request Types](#how-to-create-request-types)
- [How To Create Response Types](#how-to-create-response-types)
- [How To Map A Type Field To A Different Model Column](#how-to-map-a-type-field-to-a-different-model-column)
- [How Filtering And Ordering Work](#how-filtering-and-ordering-work)
- [How Aggregate Stats Work](#how-aggregate-stats-work)
- [How Nested Responses Work](#how-nested-responses-work)
- [How Custom Actions Work](#how-custom-actions-work)
- [How ACL Works](#how-acl-works)
- [How Errors Look](#how-errors-look)
- [How Pagination Works](#how-pagination-works)
- [How Docs Generation Works](#how-docs-generation-works)
- [Recommended Project Structure](#recommended-project-structure)
- [A Complete Example](#a-complete-example)
- [What To Read Next](#what-to-read-next)

---

## What CRUDFactory Is

CRUDFactory is a library you use inside a normal Django app.

It helps you generate REST API endpoints from:

- a Django model
- one or more Python dataclasses
- optional metadata attached to dataclass fields

Instead of writing many serializers, viewsets, filter backends, and response
mapping functions by hand for every resource, you declare the API contract in a
small number of structured Python types.

## Why This Library Exists

In many Django backends, CRUD endpoints repeat the same work:

- define a serializer for create
- define a serializer for update
- define a serializer for patch
- define a serializer for the response
- define a ViewSet
- wire list, retrieve, create, update, patch, delete
- re-add validation and filtering rules

That is a lot of boilerplate when the endpoint is mostly straightforward.

CRUDFactory exists to reduce that repetition while keeping the API explicit and
typed.

## How To Install The Library

If you are new to Python packaging, the simplest mental model is this:

- the library code lives in this repository
- your Django project needs that code installed into its Python environment

The normal install command is:

```bash
pip install -e .
```

What that means:

- `pip` installs the package into your environment
- `-e` means “editable install”
- editable means changes you make in this repository are immediately reflected
  in the environment without reinstalling every time

If you want OpenAPI schema support too:

```bash
pip install -e ".[schema]"
```

If you cloned the repository and want the local development environment first,
you can also use the helper scripts:

Unix/macOS:

```bash
bash scripts/setup_venv.sh
```

Windows:

```bat
scripts\setup_venv.bat
```

Those scripts create a virtual environment and install the package in editable
mode.

## How To Configure Django

There are two common ways to use CRUDFactory.

### Mode 1: CRUDFactory without the built-in ACL system

In this mode, CRUDFactory is just a library for typed CRUD generation.

You install it and import it in your Django app, but you do not need the
library’s database tables.

### Mode 2: CRUDFactory with the built-in ACL system

In this mode, you use the ACL tables, ACL service, ACL backend, bootstrap
helpers, and management commands provided by the library.

If you want the built-in ACL system, add `crudfactory` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "crudfactory",
]
```

If you also want OpenAPI docs:

```python
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "drf_spectacular",
    "crudfactory",
]
```

And:

```python
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
```

## How ACL Configuration Works

CRUDFactory was designed with this ACL system in mind, but the ACL layer is
still optional.

You can use CRUDFactory with no ACL at all.

You can also use CRUDFactory with a different ACL system if you implement the
expected backend protocol.

### Default behavior

If you add `crudfactory` to `INSTALLED_APPS` and run migrations normally, the
ACL models and commands are available.

### Optional startup settings

CRUDFactory now supports Django settings for ACL operativity and automatic ACL
table creation.

Recommended setting style:

```python
CRUDFACTORY = {
    "ACL_ENABLED": True,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

Meaning:

- `ACL_ENABLED`
  Turns the built-in Django ACL backend behavior on or off.

- `ACL_AUTO_CREATE_TABLES`
  If `True`, CRUDFactory will create any missing ACL tables at Django startup
  when the app is loaded.

### Recommended values

For most real projects:

```python
CRUDFACTORY = {
    "ACL_ENABLED": True,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

Then use normal Django migrations:

```bash
python -m django migrate
```

### When automatic table creation helps

Automatic ACL table creation is useful when:

- a developer wants the ACL tables available immediately in a local environment
- a quick prototype should work without remembering to run ACL migrations first
- a project wants the built-in ACL system to be more plug-and-play

### Important caution

Automatic table creation is a convenience feature.

For production systems, normal migrations are still the better default because
they are explicit, reviewable, and predictable.

### If you do not want ACL at all

Set:

```python
CRUDFACTORY = {
    "ACL_ENABLED": False,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

In that case:

- the built-in Django ACL backend will behave as disabled
- ACL table auto-creation will not run
- you can still use the normal CRUD generation parts of the library

## Core Idea

CRUDFactory works like this:

```text
request JSON
  -> generated DRF serializer
  -> request dataclass instance
  -> generated write logic or explicit handler
  -> Django model instance
  -> generated or explicit response dataclass
  -> JSON response
```

The important part is:

- request dataclasses define input
- response dataclasses define output
- metadata defines validation, mapping, filtering, ordering, stats, and more

## What A Type Is In CRUDFactory

When we say “type” in CRUDFactory, we usually mean a Python dataclass used as a
contract.

Example:

```python
from dataclasses import dataclass


@dataclass
class ItemWriteFields:
    name: str
    quantity: int
```

This dataclass is a type.

It tells CRUDFactory:

- which fields exist
- what their Python types are
- and, if metadata is attached, what rules apply to them

In practice, types in CRUDFactory are used for:

- create input
- update input
- patch input
- response output
- nested response blocks
- stats blocks
- custom action input
- custom action output

## Why There Are Different Types For Create Update And Patch

These actions do not mean the same thing.

### Create

Create means:

- build a new object
- usually needs all required creation fields
- may allow fields that should never be changed later

### Update

Update means:

- replace the full editable state
- often expects all editable fields
- should not usually include create-only fields, for example a user's password

### Patch

Patch means:

- change only part of the object
- fields are commonly optional
- omitted fields should stay unchanged

Because these actions have different semantics, it is often useful to model
them with different dataclass types.

That said, CRUDFactory can derive those different action types automatically
from one simpler source type when your resource is straightforward.

## The Main Kinds Of Types

You will usually encounter these type roles:

### Request-side types

- `write_input`
- `create_only_input`
- `create_input`
- `update_input`
- `partial_update_input`

### Response-side types

- `response_dataclass`
- nested child response dataclasses
- nested stats dataclasses

### Action types

- detail action input dataclasses
- detail action response dataclasses
- collection action input/output dataclasses

## The Shortest Working Setup

This is the smallest useful CRUDFactory resource.

### Django model

```python
from django.db import models


class InventoryItem(models.Model):
    name = models.CharField(max_length=80)
    quantity = models.IntegerField(default=0)
```

### Writable type

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

### Factory

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

### URLs

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

## The Most Important CRUDFactory Parameters

The constructor can take many arguments, but most users only need to understand
the main ones first.

### `model`

The Django model that stores the resource.

### `create_input`

The dataclass type used for `POST` request bodies.

### `update_input`

The dataclass type used for `PUT` request bodies.

### `partial_update_input`

The dataclass type used for `PATCH` request bodies.

### `response_mapper`

A function that takes a model instance and returns the response dataclass
instance.

Use this when the response shape is not simple enough to be derived
automatically.

### `response_dataclass`

An explicit response type declaration used when the library can automatically
build the mapper from the response type itself.

### `create_handler`, `update_handler`, `partial_update_handler`

Optional write hooks for create, update, and patch.

Use these when your write logic is more than “assign these fields to this
model”.

### `writable_fields`

An allowlist for automatic writes.

If omitted, CRUDFactory derives the writable fields from the input DTOs.

### `custom_actions`

Typed non-CRUD endpoints, such as:

- start
- stop
- unlock
- activate
- bulk import

### `acl`

The ACL configuration for the factory.

### `queryset`

An explicit Django queryset to use for the resource.

This is useful when you want `select_related`, `prefetch_related`, or a
pre-filtered dataset.

### `route`

The URL route prefix.

Example:

```python
route="connectors"
```

usually means endpoints under:

```text
/connectors/
```

### `basename`

The DRF router basename.

This affects internal route naming.

### `app_name`

The Django app namespace used when mounting the generated URLs.

## How Automatic CRUD Works

When you pass:

```python
factory = CRUDFactory(
    model=InventoryItem,
    write_input=ItemWriteFields,
)
```

CRUDFactory automatically derives:

- create input type
- update input type
- patch input type
- DRF serializers for those inputs
- simple create/update/patch write logic
- a response type based on the update fields

This is the most compact mode of the library.

## When Minimal Mode Is Enough

Minimal mode is enough when:

- one endpoint maps cleanly to one Django model
- the client-facing field names match the model field names
- the write is just field assignment on that model
- the response can be generated from the same fields
- there is no complex business logic in create/update/patch

## When You Need Explicit Types

Use more explicit configuration when:

- create has fields that update should not accept
- response shape differs from request shape
- response includes related model fields
- response includes nested child lists
- response includes aggregate stats
- writes touch multiple models
- you need custom actions
- you need ACL checks

Typical explicit form:

```python
factory = CRUDFactory(
    model=Chargepoint,
    create_only_input=ChargepointCreateOnlyFields,
    write_input=ChargepointMutableFields,
    response_dataclass=ChargepointResponseDTO,
)
```

## The Metadata System

The metadata system is what makes CRUDFactory powerful.

Each dataclass field can carry metadata that says things like:

- validate with regex
- validate min/max length
- validate numeric range
- map this API field to a different model field
- allow filtering on this field
- allow ordering on this field
- derive this field from a related model lookup
- compute this field from an aggregate stat

CRUDFactory recommends grouped metadata helper classes so autocomplete is
easier and imports stay small.

The main classes are:

- `RequestConstraints`
- `RequestFilter`
- `RequestMapping`
- `ResponseField`
- `ResponseStats`

## RequestConstraints

Use `RequestConstraints` for input validation.

Available methods:

- `.regex(...)`
- `.length(...)`
- `.range(...)`
- `.choices(...)`

Example:

```python
name: str = field(
    metadata=RequestConstraints.regex(r"^[A-Za-z ]+$").length(min=2, max=80)
)
quantity: int = field(
    metadata=RequestConstraints.range(min=0, max=500)
)
status: str = field(
    metadata=RequestConstraints.choices(["online", "offline", "faulted"])
)
```

## RequestFilter

Use `RequestFilter` on response fields to allow list filtering and ordering.

Available methods:

- `.filterable(...)`
- `.orderable(...)`
- `.sortable(...)`

Example:

```python
name: str = field(
    metadata=RequestFilter.filterable(lookups=("exact", "icontains")).orderable()
)
```

This lets the client call things like:

```http
GET /items/?name__icontains=charger&ordering=-name
```

## RequestMapping

Use `RequestMapping` when the API field name differs from the Django model
field name.

Example:

```python
public_name: str = field(
    metadata=RequestMapping.model_field("name")
)
```

This means:

- the API receives `public_name`
- the Django model stores the value in `name`

It can also apply read and write transforms:

```python
price: str = field(
    metadata=RequestMapping.model_field(
        "price_cents",
        read_transform=lambda cents: f"{cents / 100:.2f}",
        write_transform=lambda dollars: int(float(dollars) * 100),
    )
)
```

## ResponseField

Use `ResponseField` for response-side mapping.

### Map from another model field

```python
location_name: str = field(
    metadata=ResponseField.from_model("chargepoint__location__name")
)
```

### Map a related child list

```python
connectors: list[ConnectorDTO] = field(
    metadata=ResponseField.related_list("connectors")
)
```

This is what allows nested read responses without manually writing a mapper for
every case.

## ResponseStats

Use `ResponseStats` for per-object aggregate stats.

Available methods:

- `ResponseStats.count(...)`
- `ResponseStats.sum(...)`
- `ResponseStats.avg(...)`
- `ResponseStats.min(...)`
- `ResponseStats.max(...)`

Example:

```python
from django.db.models import Q


@dataclass
class StatusStatsDTO:
    online: int = ResponseStats.count(
        "connectors",
        filter=Q(connectors__status="online"),
    )
    faulted: int = ResponseStats.count(
        "connectors",
        filter=Q(connectors__status="faulted"),
    )
```

CRUDFactory will annotate the queryset and fill those fields automatically.

## How To Create Request Types

There are three common styles.

### Style 1: One `write_input`

Best for simple resources.

```python
factory = CRUDFactory(
    model=InventoryItem,
    write_input=ItemWriteFields,
)
```

### Style 2: `create_only_input` plus `write_input`

Best when create requires extra fields.

```python
factory = CRUDFactory(
    model=Chargepoint,
    create_only_input=ChargepointCreateOnlyFields,
    write_input=ChargepointMutableFields,
)
```

### Style 3: Fully explicit action types

Best when all actions have clearly different contracts.

```python
factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
)
```

## How To Create Response Types

There are two main styles.

### Automatic response

If you omit `response_dataclass` and `response_mapper`, CRUDFactory can derive a
response type from the update/write input.

### Explicit response

Use `response_dataclass=...` when:

- you need related fields
- you need nested child lists
- you need stats
- you want a response that does not mirror the write fields

Example:

```python
@dataclass
class ConnectorResponseDTO:
    id: int
    chargepoint_name: str = field(
        metadata=ResponseField.from_model("chargepoint__name")
    )
    location_name: str = field(
        metadata=ResponseField.from_model("chargepoint__location__name")
    )
    name: str
    status: str
```

## How To Map A Type Field To A Different Model Column

Use `RequestMapping.model_field(...)`.

Example:

```python
public_name: str = field(
    metadata=RequestMapping.model_field("name")
)
```

This is extremely useful when:

- the database column name is not ideal for the API
- the API wants a clearer name than the model
- legacy tables have awkward column names

## How Filtering And Ordering Work

Filtering and ordering are declared on response fields.

Example:

```python
@dataclass
class ItemResponseDTO:
    id: int
    name: str = field(
        metadata=RequestFilter.filterable(lookups=("exact", "icontains")).orderable()
    )
    quantity: int = field(
        metadata=RequestFilter.filterable(lookups=("gte", "lte")).orderable()
    )
```

This enables:

```http
GET /items/?name__icontains=charger&quantity__gte=10&ordering=-quantity
```

## How Aggregate Stats Work

Aggregate stats live inside response dataclasses.

Example:

```python
@dataclass
class ConnectorStatsDTO:
    online: int = ResponseStats.count(
        "connectors",
        filter=Q(connectors__status="online"),
    )
    offline: int = ResponseStats.count(
        "connectors",
        filter=Q(connectors__status="offline"),
    )


@dataclass
class LocationResponseDTO:
    id: int
    name: str
    stats: ConnectorStatsDTO = field(default_factory=ConnectorStatsDTO)
```

This is output-only. It does not affect request validation.

## How Nested Responses Work

Nested responses are supported for read output.

Example:

```python
@dataclass
class ChargepointConnectorDTO:
    id: int
    name: str
    status: str


@dataclass
class ChargepointResponseDTO:
    id: int
    name: str
    connectors: list[ChargepointConnectorDTO] = field(
        metadata=ResponseField.related_list("connectors")
    )
```

CRUDFactory can walk those types and generate nested output.

## How Custom Actions Work

Custom actions are typed endpoints beyond normal CRUD.

Example use cases:

- `POST /connectors/{id}/start/`
- `POST /connectors/{id}/stop/`
- `POST /connectors/{id}/unlock/`

Example:

```python
@dataclass
class ConnectorActionInputDTO:
    reason: str | None = field(default=None, metadata=RequestConstraints.length(max=80))


@dataclass
class ConnectorActionResponseDTO:
    id: int
    action: str
    status: str
    message: str
```

Then register actions with `detail_action(...)` or grouped helpers like
`detail_actions(...)`.

## How ACL Works

CRUDFactory supports ACL through:

- `crud_acl(...)`
- `DjangoACLBackend`
- `ACLResourceRef`
- `resource_ref_templates(...)`

Typical pattern:

```python
connector_acl = crud_acl(
    backend=DjangoACLBackend(),
    permission_prefix="app.connector",
    resource_ref_from_instance=...,
)
```

ACL can protect:

- list routes
- detail routes
- create/update/delete
- custom actions

Common ACL-related constructor pieces:

### `crud_acl(...)`

Convenience helper that builds normal CRUD permission mapping from a permission
prefix.

### `permission_prefix`

The shared prefix used to derive permission names.

Example:

```python
permission_prefix="app.connector"
```

This leads to permission keys like:

- `app.connector.read`
- `app.connector.create`
- `app.connector.update`
- `app.connector.delete`

### `resource_ref_from_instance`

How a model instance becomes an ACL resource reference.

### `resource_ref_from_create_input`

How create is authorized before the new object exists in the database.

### `queryset_filter`

Optional advanced hook for efficiently filtering lists by access.

## How Errors Look

Successful responses use your response DTO shape.

Non-successful responses use DRF-style error payloads.

### Validation error

```json
{
  "name": ["Ensure this field has at least 2 characters."]
}
```

### Not found

```json
{
  "detail": "Not found."
}
```

### Permission failure

Depending on ACL settings, this may be:

- `403`
- or `404` to avoid revealing resource existence

Frontend code should never assume that error payloads match success DTOs.

## How Pagination Works

CRUDFactory uses normal DRF pagination.

The helper:

```python
from crudfactory import page_number_pagination
```

lets you configure a simple page-number paginator:

```python
factory = CRUDFactory(
    ...,
    pagination_class=page_number_pagination(page_size=20, max_page_size=100),
)
```

Paginated list responses use DRF’s standard:

```json
{
  "count": 42,
  "next": "http://localhost/api/items/?page=2",
  "previous": null,
  "results": []
}
```

## How Docs Generation Works

CRUDFactory can generate:

### OpenAPI schema

If `drf-spectacular` is installed and configured.

### Markdown factory docs

Each factory can render Markdown describing:

- endpoints
- request types
- response types
- filters
- ordering
- actions
- error shapes

Example:

```python
markdown = factory.render_markdown_docs(
    title="Connector CRUD Factory",
    base_path="/api",
)
```

## Recommended Project Structure

The cleanest structure is one file per factory.

Recommended layout:

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

- request dataclasses
- response dataclasses
- queryset configuration
- ACL wiring
- custom actions
- the `CRUDFactory(...)` declaration

This keeps each resource portable and easy to understand.

## A Complete Example

```python
from dataclasses import dataclass, field
from decimal import Decimal

from crudfactory import (
    CRUDFactory,
    QueryPlan,
    RequestConstraints,
    RequestFilter,
    RequestMapping,
    ResponseField,
)


@dataclass
class ConnectorWriteFields:
    chargepoint_id: int = field(
        metadata=RequestMapping.model_field("chargepoint_id").range(min=1)
    )
    name: str = field(
        metadata=RequestConstraints.regex(r"^[A-Za-z0-9 -]+$").length(min=2, max=80)
    )
    status: str = field(
        metadata=RequestConstraints.choices(["online", "offline", "faulted", "occupied"])
    )
    power_kw: Decimal = field(metadata=RequestConstraints.range(min=0, max=500))


@dataclass
class ConnectorResponseDTO:
    id: int
    chargepoint_name: str = field(
        metadata=ResponseField.from_model("chargepoint__name")
        .filterable("chargepoint__name", lookups=("exact", "icontains"))
        .orderable("chargepoint__name")
    )
    location_name: str = field(
        metadata=ResponseField.from_model("chargepoint__location__name")
        .filterable("chargepoint__location__name", lookups=("exact", "icontains"))
        .orderable("chargepoint__location__name")
    )
    name: str = field(
        metadata=RequestFilter.filterable(lookups=("exact", "icontains")).orderable()
    )
    status: str = field(
        metadata=RequestFilter.filterable(lookups=("exact",)).orderable()
    )
    power_kw: Decimal = field(metadata=RequestFilter.orderable())


connector_factory = CRUDFactory(
    model=Connector,
    write_input=ConnectorWriteFields,
    response_dataclass=ConnectorResponseDTO,
    queryset_plan=QueryPlan().select("chargepoint__location").order_by("id"),
    route="connectors",
    basename="connector",
    app_name="inventory",
)
```

## What To Read Next

This page is meant to be self-contained, but the supporting pages are still
useful:

- [CRUDFactory](CRUDFactory.md)
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
