# Validation Helpers

CRUDFactory exports four small helpers for request DTO validation:

- `regex(...)`
- `length(...)`
- `range_(...)`
- `choices(...)`

These helpers do not replace `dataclasses.field(...)`. They return metadata
dictionaries that you attach to a dataclass field.

## `regex(pattern, message=None)`

Use this on string fields that must match a regular expression.

```python
name: str = field(metadata=regex(r"^[A-Za-z0-9 -]+$"))
```

You can provide a custom message:

```python
slug: str = field(
    metadata=regex(r"^[a-z0-9-]+$", message="Slug may only contain lowercase letters, numbers, and dashes.")
)
```

## `length(min=None, max=None)`

Use this on strings or lists when the number of items or characters matters.

```python
name: str = field(metadata=length(min=2, max=80))
tags: list[str] = field(metadata=length(max=10))
```

At least one of `min` or `max` is required.

## `range_(min=None, max=None)`

Use this on values that should stay within a numeric or date range.

Supported kinds include:

- `int`
- `float`
- `Decimal`
- `date`
- `datetime`

```python
quantity: int = field(metadata=range_(min=0, max=500))
price: Decimal = field(metadata=range_(min=Decimal("0")))
```

At least one of `min` or `max` is required.

## `choices(values)`

Use this when only a fixed list of values is allowed.

```python
status: str = field(metadata=choices(["online", "offline", "faulted"]))
priority: int = field(metadata=choices([1, 2, 3]))
```

## Combining Helpers

You can merge metadata dictionaries with dictionary unpacking:

```python
name: str = field(
    metadata={
        **regex(r"^[A-Za-z ]+$"),
        **length(min=2, max=80),
    }
)
```

## Related Pages

- [Home](Home.md)
- [CRUDFactory](CRUDFactory.md)
