from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from django.db import models

from .stats import AggregateStatSpec, apply_stat_values_to_response_data
from .types import M, ResponseDTO, ResponseMapper

__all__: list[str] = []


def map_instance_to_response_dataclass(
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
) -> ResponseDTO:
    """Return the response dataclass produced by the user's mapper.

    This function is intentionally tiny.  Keeping it separate gives the public
    factory a readable method name while making the response flow explicit:
    model instance -> user mapper -> response DTO.
    """
    return response_mapper(instance)


def map_instance_to_response_data(
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...] = (),
) -> dict[str, object]:
    """Return JSON-ready response data for one model instance.

    CRUDFactory uses dataclasses as its successful response contract.  The
    mapper must therefore return a dataclass instance, not a dataclass class and
    not an arbitrary object.  `asdict` gives DRF a plain dictionary that can be
    rendered by the configured renderer.
    """
    dto = map_instance_to_response_dataclass(instance, response_mapper)
    ensure_dataclass_instance(dto)
    data = cast(dict[str, object], asdict(cast(Any, dto)))
    return apply_stat_values_to_response_data(
        data=data,
        instance=instance,
        stat_specs=stat_specs,
    )


def ensure_dataclass_instance(value: object) -> None:
    """Fail early when a response mapper returns the wrong shape."""
    if not is_dataclass(value) or isinstance(value, type):
        msg = (
            "response_mapper must return a dataclass instance at runtime. "
            f"Got {type(value).__name__}: {value!r}."
        )
        raise TypeError(msg)


def dataclass_instance_to_response_data(value: object) -> dict[str, object]:
    """Return JSON-ready data for a dataclass returned by a custom action."""
    ensure_dataclass_instance(value)
    return cast(dict[str, object], asdict(cast(Any, value)))
