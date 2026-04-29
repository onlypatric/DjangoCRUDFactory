# page_number_pagination

`page_number_pagination(...)` is a small helper that returns a DRF
`PageNumberPagination` class for one factory.

Use it when you want the normal DRF page-number style but do not want to write
a custom pagination class by hand.

## Example

```python
from crudfactory import CRUDFactory, page_number_pagination


factory = CRUDFactory(
    model=InventoryItem,
    create_input=ItemCreateDTO,
    update_input=ItemUpdateDTO,
    partial_update_input=ItemPatchDTO,
    pagination_class=page_number_pagination(page_size=25),
)
```

## Parameters

- `page_size=20`
  Default number of results per page.

- `page_query_param="page"`
  Query parameter name for the page number.

- `page_size_query_param="page_size"`
  Optional query parameter name for client-controlled page size.

- `max_page_size=100`
  Maximum page size clients may request.

## Related Pages

- [Home](Home.md)
- [CRUDFactory](CRUDFactory.md)
