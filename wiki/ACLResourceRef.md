# ACLResourceRef

`ACLResourceRef` is the concrete resource reference type used by the Django ACL
backend in this repository.

It is the object passed into resource-scoped permission checks.

## Purpose

A permission backend often needs more than just a raw integer primary key.

It may need:

- resource type
- resource key

`ACLResourceRef` captures that pair in a clear typed object.

## Typical Shape

It usually represents:

- `resource_type`
- `resource_key`

For example:

```python
ACLResourceRef("connector", "CP-001/1")
```

## Where It Is Used

Commonly in:

- `resource_ref_from_instance`
- `resource_ref_from_create_input`
- custom action ACL configuration

## Example

```python
resource_ref_from_instance=lambda connector: ACLResourceRef(
    "connector",
    f"{connector.chargepoint.serial_number}/{connector.name}",
)
```

## Why Not Use A Plain String

Using a dedicated class is clearer and safer:

- resource kind is explicit
- key structure is explicit
- different resource domains are easier to distinguish
