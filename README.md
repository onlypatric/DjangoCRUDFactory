# CRUDFactory

CRUDFactory is a Django REST Framework library that generates typed CRUD APIs
from Django models and Python dataclasses.

It is designed to reduce repetitive DRF CRUD boilerplate while keeping the API
contract explicit and typed.

The library is a good fit when you want:

- typed request DTOs
- typed response DTOs
- less serializer and viewset boilerplate
- optional filtering, ordering, stats, custom actions, and ACL wiring
- the ability to stay minimal for simple resources and go explicit for complex ones

This README is the short project overview. The full documentation lives in the
GitHub wiki, with `Home.md` as the main manual.

## Index

- [What The Project Is](#what-the-project-is)
- [Installation](#installation)
- [Django Setup](#django-setup)
- [Quick Example](#quick-example)
- [What CRUDFactory Can Generate](#what-crudfactory-can-generate)
- [Built-In ACL Support](#built-in-acl-support)
- [How To Read The Full Docs](#how-to-read-the-full-docs)

## What The Project Is

CRUDFactory is a productivity layer on top of Django REST Framework.

You describe an API resource with:

- a Django model
- request dataclasses
- a response dataclass or response mapper
- optional field metadata

and CRUDFactory generates the repetitive pieces around that contract.

At its simplest, it is built for this kind of setup:

```python
factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
)
```

## Installation

Editable install from this repository:

```bash
pip install -e .
```

If you want OpenAPI schema support too:

```bash
pip install -e ".[schema]"
```

You can also bootstrap a local virtual environment with the included scripts.

Unix or macOS:

```bash
bash scripts/setup_venv.sh
```

Windows:

```bat
scripts\setup_venv.bat
```

## Django Setup

If you only want CRUD generation, install the package and import it in your
app code.

If you want the built-in ACL system too, add `crudfactory` to
`INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "crudfactory",
]
```

Recommended ACL settings:

```python
CRUDFACTORY = {
    "ACL_ENABLED": True,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

Then run:

```bash
python -m django migrate
```

## Quick Example

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

That gives you the normal CRUD routes plus generated validation and simple
single-model writes.

## What CRUDFactory Can Generate

Depending on how much configuration you provide, CRUDFactory can generate:

- CRUD routes
- request validation from dataclass metadata
- automatic simple writes
- automatic or explicit response DTO output
- filtering and ordering
- aggregate stats
- typed custom actions
- OpenAPI schema integration
- Markdown factory docs
- ACL-aware queryset and object checks

## Built-In ACL Support

ACL is optional.

If you use the built-in ACL system, CRUDFactory ships:

- ACL Django models
- a Django-backed ACL backend
- bootstrap helpers
- management commands
- automatic integration points for generated CRUD endpoints

If you do not want ACL, disable it in settings:

```python
CRUDFACTORY = {
    "ACL_ENABLED": False,
    "ACL_AUTO_CREATE_TABLES": False,
}
```

## How To Read The Full Docs

Use the wiki as the canonical documentation set.

Start with:

- `Home.md` in the wiki for the full manual
- `CRUDFactory.md` for the main class reference
- the helper reference pages for validation, filtering, mapping, stats, custom actions, pagination, and ACL

The README is intentionally shorter than the wiki and should stay that way.
