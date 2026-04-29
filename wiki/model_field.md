# model_field

`model_field(...)` maps a DTO field name to a different Django model field
name.

This matters when:

- the public API field name differs from the model field name
- the response reads from a related lookup
- you need a read or write transform

## Basic Usage

```python
public_name: str = field(metadata=model_field("name"))
```

Meaning:

- DTO field: `public_name`
- Django field: `name`

## Read And Write Transforms

```python
price: str = field(
    metadata=model_field(
        "price_cents",
        read_transform=lambda cents: f"{cents / 100:.2f}",
        write_transform=lambda euros: int(float(euros) * 100),
    )
)
```

Use transforms carefully. They are best for small, obvious conversions.

## Related Lookups In Responses

For response DTOs, the mapped field may point at a related lookup:

```python
chargepoint_name: str = field(metadata=model_field("chargepoint__name"))
location_name: str = field(metadata=model_field("chargepoint__location__name"))
```

## Related Pages

- [Home](Home.md)
- [Filtering And Ordering](Filtering-And-Ordering.md)
