from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["compose_meta"]


def compose_meta(*fragments: Mapping[str, object]) -> dict[str, object]:
    """Merge dataclass metadata fragments into one metadata dictionary.

    Usage:

    ```python
    field(
        metadata=compose_meta(
            model_field("status"),
            filterable(lookups=("exact",)),
            orderable(),
        )
    )
    ```

    The helper is intentionally strict: duplicate metadata keys are rejected so
    DTO declarations fail early instead of silently overriding one fragment with
    another.
    """
    combined: dict[str, object] = {}
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, Mapping):
            msg = (
                "compose_meta expects metadata mappings. "
                f"Fragment {index} is {type(fragment).__name__}."
            )
            raise TypeError(msg)
        for key, value in fragment.items():
            if key in combined:
                msg = (
                    "compose_meta received duplicate metadata key "
                    f"{key!r}. Merge fragments explicitly or remove the overlap."
                )
                raise ValueError(msg)
            combined[key] = value
    return combined
