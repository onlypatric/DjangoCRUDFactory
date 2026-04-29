# ACLConfig

`ACLConfig` is the full ACL configuration attached to a `CRUDFactory`.

It tells CRUDFactory:

- which permissions to use for each action
- how to resolve the current actor
- how to resolve a target resource
- how to filter querysets for scoped list access

## What It Contains

An `ACLConfig` may define:

- `list_action`
- `retrieve_action`
- `create_action`
- `update_action`
- `partial_update_action`
- `destroy_action`
- `list_filter_mode`
- `actor_resolver`
- `resource_ref_from_instance`
- `resource_ref_from_create_input`
- `resource_ref_from_update_input`
- `resource_ref_from_patch_input`
- `queryset_filter`

## Why It Exists

CRUDFactory cannot guess:

- how your permission keys are named
- how a model instance maps to a resource identifier
- how a create DTO should be authorized before the object exists

`ACLConfig` is the structure that makes those decisions explicit.

## Typical Construction

Most users create it with:

```python
crud_acl(...)
```

instead of instantiating `ACLConfig` manually.

## Important Resource Resolvers

### `resource_ref_from_instance`

Used for:

- retrieve
- destroy
- and often update/patch

### `resource_ref_from_create_input`

Used for create authorization before the model instance exists.

### `resource_ref_from_update_input`

Used when the update payload itself affects which resource should be checked.

### `resource_ref_from_patch_input`

Equivalent concept for partial updates.

## List Filtering

`list_filter_mode` controls what happens when list access is scoped:

- filter unauthorized rows out
- or forbid the entire request

## Related Classes

- [ACLActionConfig](ACLActionConfig.md)
- [ACLBackend](ACLBackend.md)
- [DjangoACLBackend](DjangoACLBackend.md)
