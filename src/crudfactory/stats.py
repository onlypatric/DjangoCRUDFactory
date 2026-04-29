from __future__ import annotations

from dataclasses import Field, dataclass, field, fields, is_dataclass
from types import UnionType
from typing import Any, Callable, Union, cast, get_args, get_origin, get_type_hints

from django.db import models
from django.db.models import Avg, Count, Max, Min, Q, Sum

from .filters import response_dataclass_from_mapper
from .types import M

STAT_METADATA_KEY = "crudfactory_stat"

__all__ = [
    "AggregateStatSpec",
    "avg_stat",
    "count_stat",
    "max_stat",
    "min_stat",
    "sum_stat",
]


@dataclass(frozen=True)
class AggregateStatDeclaration:
    """The aggregate requested by one response dataclass field.

    This declaration is stored directly in dataclass field metadata.  It does
    not know where the field lives in the response DTO tree yet; discovery adds
    that path later when it walks the response mapper's return annotation.
    """

    aggregate_name: str
    lookup: str
    filter: Q | None
    distinct: bool
    default: object


@dataclass(frozen=True)
class AggregateStatSpec:
    """A discovered aggregate stat field ready to become a queryset annotation.

    `path` is the response DTO path that must be filled, for example
    `("stats", "online")`.

    `alias` is the private Django annotation name added to each model instance.
    It is intentionally verbose to avoid colliding with real model fields.
    """

    path: tuple[str, ...]
    alias: str
    declaration: AggregateStatDeclaration


def count_stat(
    lookup: str,
    *,
    filter: Q | None = None,
    distinct: bool = False,
) -> Any:
    """Return a dataclass field that counts related rows for one response stat."""
    return stat_field(
        AggregateStatDeclaration(
            aggregate_name="count",
            lookup=lookup,
            filter=filter,
            distinct=distinct,
            default=0,
        )
    )


def sum_stat(
    lookup: str,
    *,
    filter: Q | None = None,
    default: object = 0,
) -> Any:
    """Return a dataclass field that sums related values for one response stat."""
    return stat_field(
        AggregateStatDeclaration(
            aggregate_name="sum",
            lookup=lookup,
            filter=filter,
            distinct=False,
            default=default,
        )
    )


def avg_stat(
    lookup: str,
    *,
    filter: Q | None = None,
    default: object = None,
) -> Any:
    """Return a dataclass field that averages related values for one response stat."""
    return stat_field(
        AggregateStatDeclaration(
            aggregate_name="avg",
            lookup=lookup,
            filter=filter,
            distinct=False,
            default=default,
        )
    )


def min_stat(
    lookup: str,
    *,
    filter: Q | None = None,
    default: object = None,
) -> Any:
    """Return a dataclass field that finds the minimum related value."""
    return stat_field(
        AggregateStatDeclaration(
            aggregate_name="min",
            lookup=lookup,
            filter=filter,
            distinct=False,
            default=default,
        )
    )


def max_stat(
    lookup: str,
    *,
    filter: Q | None = None,
    default: object = None,
) -> Any:
    """Return a dataclass field that finds the maximum related value."""
    return stat_field(
        AggregateStatDeclaration(
            aggregate_name="max",
            lookup=lookup,
            filter=filter,
            distinct=False,
            default=default,
        )
    )


def stat_field(declaration: AggregateStatDeclaration) -> Field[Any]:
    """Create the dataclass field used by every public stat helper."""
    return cast(
        Field[Any],
        field(
            default=declaration.default,
            metadata={STAT_METADATA_KEY: declaration},
        ),
    )


def stat_specs_from_response_mapper(
    response_mapper: Callable[..., object],
) -> tuple[AggregateStatSpec, ...]:
    """Discover aggregate stat fields from the mapper's return dataclass."""
    response_type = response_dataclass_from_mapper(response_mapper)
    if response_type is None:
        return ()
    return stat_specs_from_dataclass(response_type)


def stat_specs_from_dataclass(
    dataclass_type: type[Any],
) -> tuple[AggregateStatSpec, ...]:
    """Return all aggregate stat fields declared anywhere in a response DTO."""
    return tuple(walk_dataclass_stat_specs(dataclass_type, path=()))


def walk_dataclass_stat_specs(
    dataclass_type: type[Any],
    *,
    path: tuple[str, ...],
) -> list[AggregateStatSpec]:
    """Recursively collect aggregate stat metadata from nested dataclasses."""
    specs: list[AggregateStatSpec] = []
    type_hints = get_type_hints(dataclass_type)

    for dataclass_field in fields(dataclass_type):
        field_path = (*path, dataclass_field.name)
        if field_has_stat(dataclass_field):
            specs.append(stat_spec_from_field(dataclass_field, field_path))

        nested_dataclass_type = dataclass_type_from_annotation(
            type_hints.get(dataclass_field.name, dataclass_field.type)
        )
        if nested_dataclass_type is not None:
            specs.extend(
                walk_dataclass_stat_specs(
                    nested_dataclass_type,
                    path=field_path,
                )
            )

    return specs


def field_has_stat(dataclass_field: Field[Any]) -> bool:
    """Return True when a response field is backed by a Django aggregate."""
    return STAT_METADATA_KEY in dataclass_field.metadata


def stat_spec_from_field(
    dataclass_field: Field[Any],
    path: tuple[str, ...],
) -> AggregateStatSpec:
    """Convert one dataclass field metadata declaration into a stat spec."""
    metadata_value = dataclass_field.metadata[STAT_METADATA_KEY]
    if not isinstance(metadata_value, AggregateStatDeclaration):
        msg = (
            f"Invalid stat metadata for {'.'.join(path)!r}. "
            "Use count_stat(), sum_stat(), avg_stat(), min_stat(), or max_stat()."
        )
        raise TypeError(msg)
    return AggregateStatSpec(
        path=path,
        alias=annotation_alias_for_path(path),
        declaration=metadata_value,
    )


def annotation_alias_for_path(path: tuple[str, ...]) -> str:
    """Return a private, stable queryset annotation alias for a response path."""
    return "_crudfactory_stat__" + "__".join(path)


def dataclass_type_from_annotation(annotation: object) -> type[Any] | None:
    """Return the dataclass type represented by an annotation, if any."""
    unwrapped_annotation = unwrap_optional_annotation(annotation)
    if isinstance(unwrapped_annotation, type) and is_dataclass(unwrapped_annotation):
        return unwrapped_annotation
    return None


def unwrap_optional_annotation(annotation: object) -> object:
    """Return the inner type for Optional[T] and T | None annotations."""
    origin = get_origin(annotation)
    if origin not in (Union, UnionType):
        return annotation

    args = tuple(arg for arg in get_args(annotation) if arg is not type(None))
    if len(args) == 1:
        return args[0]
    return annotation


def annotate_queryset_with_stat_specs(
    queryset: models.QuerySet[M],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> models.QuerySet[M]:
    """Add all configured aggregate stat annotations to a queryset."""
    if not stat_specs:
        return queryset

    annotations = {
        stat_spec.alias: aggregate_expression_for_spec(stat_spec)
        for stat_spec in stat_specs
    }
    return queryset.annotate(**annotations)


def aggregate_expression_for_spec(stat_spec: AggregateStatSpec) -> Any:
    """Build the Django aggregate expression for one discovered stat spec."""
    declaration = stat_spec.declaration
    if declaration.aggregate_name == "count":
        return Count(
            declaration.lookup,
            filter=declaration.filter,
            distinct=declaration.distinct,
        )

    kwargs = aggregate_kwargs(declaration)
    if declaration.aggregate_name == "sum":
        return Sum(declaration.lookup, **kwargs)
    if declaration.aggregate_name == "avg":
        return Avg(declaration.lookup, **kwargs)
    if declaration.aggregate_name == "min":
        return Min(declaration.lookup, **kwargs)
    if declaration.aggregate_name == "max":
        return Max(declaration.lookup, **kwargs)

    msg = f"Unsupported aggregate stat type {declaration.aggregate_name!r}."
    raise TypeError(msg)


def aggregate_kwargs(declaration: AggregateStatDeclaration) -> dict[str, Any]:
    """Return keyword arguments shared by non-count aggregate expressions."""
    kwargs: dict[str, Any] = {"filter": declaration.filter}
    if declaration.default is not None:
        kwargs["default"] = declaration.default
    return kwargs


def instance_with_stat_annotations(
    *,
    instance: M,
    queryset: models.QuerySet[M],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> M:
    """Return a fresh copy of `instance` carrying aggregate stat annotations."""
    if not stat_specs:
        return instance

    primary_key = instance.pk
    if primary_key is None:
        return instance

    annotated_queryset = annotate_queryset_with_stat_specs(queryset, stat_specs)
    annotated_instance = annotated_queryset.filter(pk=primary_key).first()
    if annotated_instance is None:
        return instance
    return cast(M, annotated_instance)


def apply_stat_values_to_response_data(
    *,
    data: dict[str, Any],
    instance: models.Model,
    stat_specs: tuple[AggregateStatSpec, ...],
) -> dict[str, Any]:
    """Fill stat fields in response data from private model annotations."""
    for stat_spec in stat_specs:
        if not hasattr(instance, stat_spec.alias):
            continue
        set_nested_response_value(
            data=data,
            path=stat_spec.path,
            value=getattr(instance, stat_spec.alias),
        )
    return data


def set_nested_response_value(
    *,
    data: dict[str, Any],
    path: tuple[str, ...],
    value: object,
) -> None:
    """Set a nested key inside response data, creating dict parents as needed."""
    current: dict[str, Any] = data
    for key in path[:-1]:
        nested = current.get(key)
        if not isinstance(nested, dict):
            nested = {}
            current[key] = nested
        current = nested
    current[path[-1]] = value
