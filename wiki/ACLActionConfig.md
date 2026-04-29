# ACLActionConfig

`ACLActionConfig` describes ACL behavior for one action.

Example actions:

- list
- retrieve
- create
- update
- partial update
- destroy
- custom action

## Fields

### `permission`

The permission key to check.

Example:

```python
"app.connector.update"
```

### `mode`

How ACL should be evaluated.

Supported values:

- `"global"`
- `"scoped"`
- `"disabled"`

### `unauthorized_as_404`

If `True`, unauthorized detail access can return `404` instead of `403`.

This is useful when you do not want to reveal that a resource exists.

## Typical Use

Most users do not build these manually for normal CRUD.

Instead they use:

- `crud_acl(...)`

That helper generates a full set of `ACLActionConfig` objects for CRUD actions.

You are more likely to create `ACLActionConfig` yourself for:

- custom actions
- unusual permission names
- mixing global and scoped modes
