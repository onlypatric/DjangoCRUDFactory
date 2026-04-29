# Aggregate Stats

CRUDFactory can annotate queryset-backed aggregate values and expose them
through response DTO fields.

The exported helpers are:

- `count_stat(...)`
- `sum_stat(...)`
- `avg_stat(...)`
- `min_stat(...)`
- `max_stat(...)`

## Basic Example

```python
from dataclasses import dataclass, field

from django.db.models import Q
from crudfactory import count_stat


@dataclass
class ChargerStatsDTO:
    online: int = count_stat("connectors", filter=Q(connectors__status="online"))
    offline: int = count_stat("connectors", filter=Q(connectors__status="offline"))


@dataclass
class LocationResponseDTO:
    id: int
    name: str
    stats: ChargerStatsDTO = field(default_factory=ChargerStatsDTO)
```

CRUDFactory discovers the stat fields from the response DTO, adds queryset
annotations, and injects the values into the response.

## `count_stat(lookup, *, filter=None, distinct=False)`

Counts related rows.

## `sum_stat(lookup, *, filter=None, default=0)`

Sums related values.

## `avg_stat(lookup, *, filter=None, default=None)`

Computes an average.

## `min_stat(lookup, *, filter=None, default=None)`

Finds the minimum related value.

## `max_stat(lookup, *, filter=None, default=None)`

Finds the maximum related value.

## Notes

- Stats are output-only.
- They are discovered from the response DTO structure.
- They work well for per-object aggregates in list and detail responses.

## Related Pages

- [Home](Home.md)
- [CRUDFactory](CRUDFactory.md)
