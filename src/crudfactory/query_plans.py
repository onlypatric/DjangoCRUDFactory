from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Callable, cast, get_type_hints

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import ForeignKey, OneToOneField
from django.db.models.fields.reverse_related import ManyToManyRel, ManyToOneRel, OneToOneRel

from ._simple_writes import MODEL_FIELD_METADATA_KEY
from .filters import response_dataclass_from_mapper
from .related_collections import related_prefetches_from_response_mapper
from .stats import AggregateStatSpec
from .annotations import AnnotationSpec

__all__ = [
    "AutoQueryPlan",
    "QueryPlan",
    "apply_query_plan",
    "auto_query_plan",
    "derive_query_plan",
    "merge_query_plans",
]


@dataclass(frozen=True)
class QueryPlan:
    """A resolved queryset loading plan for one CRUDFactory resource."""

    replace_auto: bool = False
    select_related: tuple[str, ...] = ()
    prefetch_related: tuple[models.Prefetch, ...] = ()
    includes_stats: bool = False
    includes_annotations: bool = False


@dataclass(frozen=True)
class AutoQueryPlan:
    """Opt-in marker for deriving a queryset plan from response contracts."""


def auto_query_plan() -> AutoQueryPlan:
    """Return a marker that tells CRUDFactory to derive a query plan automatically."""
    return AutoQueryPlan()


def derive_query_plan(
    *,
    model: type[models.Model],
    response_mapper: Callable[..., object],
    stat_specs: tuple[AggregateStatSpec, ...] = (),
    annotation_specs: tuple[AnnotationSpec, ...] = (),
) -> QueryPlan:
    """Derive a queryset loading plan from the declared response contract."""
    return QueryPlan(
        select_related=select_related_paths_from_response_mapper(
            model=model,
            response_mapper=response_mapper,
        ),
        prefetch_related=related_prefetches_from_response_mapper(
            model=model,
            response_mapper=response_mapper,
        ),
        includes_stats=bool(stat_specs),
        includes_annotations=bool(annotation_specs),
    )


def apply_query_plan(
    queryset: models.QuerySet[Any],
    query_plan: QueryPlan,
) -> models.QuerySet[Any]:
    """Apply select_related/prefetch_related declarations to a queryset."""
    planned_queryset = queryset
    if query_plan.select_related:
        planned_queryset = planned_queryset.select_related(*query_plan.select_related)
    if query_plan.prefetch_related:
        planned_queryset = planned_queryset.prefetch_related(*query_plan.prefetch_related)
    return planned_queryset


def merge_query_plans(
    base_plan: QueryPlan,
    override_plan: QueryPlan,
) -> QueryPlan:
    """Merge two query plans, preserving order and deduplicating values."""
    return QueryPlan(
        select_related=dedupe_preserving_order(
            (*base_plan.select_related, *override_plan.select_related)
        ),
        prefetch_related=dedupe_prefetches(
            (*base_plan.prefetch_related, *override_plan.prefetch_related)
        ),
        includes_stats=base_plan.includes_stats or override_plan.includes_stats,
        includes_annotations=(
            base_plan.includes_annotations or override_plan.includes_annotations
        ),
    )


def select_related_paths_from_response_mapper(
    *,
    model: type[models.Model],
    response_mapper: Callable[..., object],
) -> tuple[str, ...]:
    """Collect forward relation chains referenced by the response dataclass."""
    response_dataclass = response_dataclass_from_mapper(response_mapper)
    if response_dataclass is None:
        return ()
    paths = walk_select_related_paths(model=model, dataclass_type=response_dataclass)
    return dedupe_preserving_order(paths)


def walk_select_related_paths(
    *,
    model: type[models.Model],
    dataclass_type: type[Any],
) -> tuple[str, ...]:
    """Recursively collect forward relation chains from a response dataclass."""
    if not is_dataclass(dataclass_type):
        return ()
    type_hints = get_type_hints(dataclass_type)
    collected: list[str] = []
    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        nested_type = nested_dataclass_type(field_type)
        raw_lookup = dataclass_field.metadata.get(
            MODEL_FIELD_METADATA_KEY,
            dataclass_field.name,
        )
        if isinstance(raw_lookup, str):
            collected.extend(select_related_prefixes_for_lookup(model=model, lookup=raw_lookup))
        if nested_type is not None:
            collected.extend(walk_select_related_paths(model=model, dataclass_type=nested_type))
    return tuple(collected)


def nested_dataclass_type(annotation: object) -> type[Any] | None:
    if isinstance(annotation, type) and is_dataclass(annotation):
        return annotation
    return None


def select_related_prefixes_for_lookup(
    *,
    model: type[models.Model],
    lookup: str,
) -> tuple[str, ...]:
    """Return the forward relation chain needed before one scalar lookup."""
    if "__" not in lookup:
        return ()
    parts = lookup.split("__")
    current_model = model
    current_prefix: list[str] = []
    collected: list[str] = []

    for part in parts[:-1]:
        relation_field = relation_field_by_name(model=current_model, relation_name=part)
        if relation_field is None:
            break
        if isinstance(relation_field, (ForeignKey, OneToOneField)):
            current_prefix.append(part)
            collected.append("__".join(current_prefix))
            current_model = cast(type[models.Model], relation_field.remote_field.model)
            continue
        if isinstance(relation_field, OneToOneRel):
            current_prefix.append(part)
            collected.append("__".join(current_prefix))
            current_model = cast(type[models.Model], relation_field.related_model)
            continue
        if isinstance(relation_field, (ManyToOneRel, ManyToManyRel)):
            break
        break

    return tuple(collected[-1:]) if collected else ()


def relation_field_by_name(
    *,
    model: type[models.Model],
    relation_name: str,
) -> object | None:
    try:
        relation_field = model._meta.get_field(relation_name)
    except FieldDoesNotExist:
        return None
    if not getattr(relation_field, "is_relation", False):
        return None
    return relation_field


def dedupe_preserving_order(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return tuple(deduped)


def dedupe_prefetches(
    prefetches: tuple[models.Prefetch, ...],
) -> tuple[models.Prefetch, ...]:
    seen: set[str] = set()
    deduped: list[models.Prefetch] = []
    for prefetch in prefetches:
        lookup = prefetch.prefetch_to
        if lookup in seen:
            continue
        seen.add(lookup)
        deduped.append(prefetch)
    return tuple(deduped)
