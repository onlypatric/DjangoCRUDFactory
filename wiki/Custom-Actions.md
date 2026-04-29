# Custom Actions

CRUDFactory supports typed custom DRF actions through:

- `detail_action(...)`
- `collection_action(...)`

These let you add extra endpoints without giving up dataclass validation or
typed responses.

## `detail_action(...)`

Creates an action bound to one resource instance.

Typical route:

```text
POST /items/{id}/activate/
```

Handler shape:

```python
def activate_item(instance: Item, dto: ActivateInputDTO) -> ActivateResponseDTO:
    ...
```

Example:

```python
activate_action = detail_action(
    name="activate",
    input_dataclass=ActivateInputDTO,
    response_dataclass=ActivateResponseDTO,
    handler=activate_item,
)
```

## `collection_action(...)`

Creates an action bound to the collection rather than one object.

Typical route:

```text
POST /items/bulk-import/
```

Handler shape:

```python
def bulk_import_items(queryset, dto: BulkImportDTO) -> BulkImportResultDTO:
    ...
```

Example:

```python
bulk_import_action = collection_action(
    name="bulk-import",
    input_dataclass=BulkImportDTO,
    response_dataclass=BulkImportResultDTO,
    handler=bulk_import_items,
)
```

## Common Parameters

- `name`
  Public action name.

- `input_dataclass`
  Request DTO for the action body.

- `response_dataclass`
  Successful response DTO.

- `handler`
  Business logic callable.

- `methods`
  HTTP methods tuple, defaulting to `("post",)`.

- `url_path`, `url_name`
  Optional DRF route naming overrides.

- `acl`
  Optional `ACLActionConfig`.

## Related Pages

- [Home](Home.md)
- [ACLActionConfig](ACLActionConfig.md)
