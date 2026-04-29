# Filtering And Ordering

CRUDFactory declares filtering and ordering on response DTO fields.

The exported helpers are:

- `filterable(...)`
- `orderable(...)`

## Why Response Fields

Filtering and ordering are public API behaviors. CRUDFactory keeps them next to
the response contract because the response DTO represents the public field names
the client sees.

## `filterable(lookup=None, *, lookups=("exact",))`

Marks one response field as filterable.

Simple field:

```python
name: str = field(metadata=filterable())
```

Related lookup:

```python
supplier_name: str = field(metadata=filterable("supplier__name"))
```

Multiple lookup operators:

```python
name: str = field(metadata=filterable(lookups=("exact", "icontains")))
quantity: int = field(metadata=filterable(lookups=("gte", "lte")))
```

Supported operators include:

- `exact`
- `iexact`
- `contains`
- `icontains`
- `startswith`
- `istartswith`
- `endswith`
- `iendswith`
- `gt`
- `gte`
- `lt`
- `lte`
- `in`
- `isnull`

## `orderable(lookup=None)`

Marks one response field as orderable.

Simple field:

```python
name: str = field(metadata=orderable())
```

Related lookup:

```python
supplier_name: str = field(metadata=orderable("supplier__name"))
```

## Combining Both

```python
name: str = field(
    metadata={
        **filterable(lookups=("exact", "icontains")),
        **orderable(),
    }
)
```

## Resulting Query Parameters

If `name` is filterable and orderable:

- `GET /items/?name=widget`
- `GET /items/?name__icontains=wid`
- `GET /items/?ordering=name`
- `GET /items/?ordering=-name`

## Related Pages

- [Home](Home.md)
- [model_field](model_field.md)
