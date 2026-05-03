from __future__ import annotations

from dataclasses import Field, dataclass, fields, is_dataclass
from typing import Any, cast, get_type_hints

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related_descriptors import ReverseManyToOneDescriptor

from ._auto_response import list_child_dataclass_type_from_annotation
from ._simple_writes import MODEL_FIELD_METADATA_KEY, model_field
from .filters import response_dataclass_from_mapper
from .types import M, ResponseDTO, ResponseMapper

RELATED_LIST_METADATA_KEY = "crudfactory_related_list"

__all__ = [
    "RELATED_LIST_METADATA_KEY",
    "RelatedListDeclaration",
    "apply_related_prefetches",
    "related_list",
    "related_prefetches_from_response_mapper",
]


@dataclass(frozen=True)
class RelatedListDeclaration:
    """Declarative loading hint for one nested response list field."""

    relation_name: str
    queryset: models.QuerySet[Any] | None = None


def related_list(
    relation_name: str,
    *,
    queryset: models.QuerySet[Any] | None = None,
) -> dict[str, object]:
    """Declare one nested response list and its optional prefetch queryset.

    This helper keeps the response field source and the loading strategy
    together. It is intended for list fields whose values come from a related
    manager or related queryset.
    """
    metadata = model_field(relation_name)
    metadata[RELATED_LIST_METADATA_KEY] = RelatedListDeclaration(
        relation_name=relation_name,
        queryset=queryset,
    )
    return metadata


def apply_related_prefetches(
    queryset: models.QuerySet[M],
    related_prefetches: tuple[models.Prefetch, ...],
) -> models.QuerySet[M]:
    """Apply declarative related-list prefetches to the base queryset."""
    if not related_prefetches:
        return queryset
    return cast(models.QuerySet[M], queryset.prefetch_related(*related_prefetches))


def related_prefetches_from_response_mapper(
    *,
    model: type[models.Model],
    response_mapper: ResponseMapper[M, ResponseDTO],
) -> tuple[models.Prefetch, ...]:
    """Collect Prefetch objects declared by the response dataclass tree."""
    response_dataclass = response_dataclass_from_mapper(response_mapper)
    if response_dataclass is None:
        return ()
    return related_prefetches_from_dataclass(
        model=model,
        dataclass_type=response_dataclass,
    )


def related_prefetches_from_dataclass(
    *,
    model: type[models.Model],
    dataclass_type: type[Any],
) -> tuple[models.Prefetch, ...]:
    """Recursively build Prefetch objects for nested response list fields."""
    ensure_response_dataclass(dataclass_type)
    type_hints = get_type_hints(dataclass_type)
    prefetches: list[models.Prefetch] = []

    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        child_dataclass = list_child_dataclass_type_from_annotation(field_type)
        if child_dataclass is None:
            continue

        lookup = relation_lookup_for_field(dataclass_field)
        related_model = related_model_for_lookup(model=model, relation_lookup=lookup)
        child_prefetches = related_prefetches_from_dataclass(
            model=related_model,
            dataclass_type=child_dataclass,
        )
        declaration = related_list_declaration_from_field(dataclass_field)
        child_queryset = queryset_for_related_prefetch(
            related_model=related_model,
            declaration=declaration,
            child_prefetches=child_prefetches,
        )
        if declaration is None and child_queryset is None:
            continue
        prefetches.append(models.Prefetch(lookup, queryset=child_queryset))

    return tuple(prefetches)


def ensure_response_dataclass(dataclass_type: type[Any]) -> None:
    if not is_dataclass(dataclass_type):
        raise TypeError(f"{dataclass_type!r} is not a dataclass type.")


def related_list_declaration_from_field(
    dataclass_field: Field[Any],
) -> RelatedListDeclaration | None:
    raw_declaration = dataclass_field.metadata.get(RELATED_LIST_METADATA_KEY)
    if raw_declaration is None:
        return None
    if isinstance(raw_declaration, RelatedListDeclaration):
        return raw_declaration
    raise TypeError(
        f"Invalid related_list metadata on response field {dataclass_field.name!r}."
    )


def relation_lookup_for_field(dataclass_field: Field[Any]) -> str:
    raw_lookup = dataclass_field.metadata.get(
        MODEL_FIELD_METADATA_KEY,
        dataclass_field.name,
    )
    if isinstance(raw_lookup, str) and raw_lookup:
        return raw_lookup
    raise TypeError(
        f"Invalid related lookup metadata on response field {dataclass_field.name!r}."
    )


def related_model_for_lookup(
    *,
    model: type[models.Model],
    relation_lookup: str,
) -> type[models.Model]:
    """Resolve the related model at the end of a Django lookup path."""
    current_model = model
    for relation_name in relation_lookup.split("__"):
        relation_field = model_relation_field_by_name(
            model=current_model,
            relation_name=relation_name,
        )
        if isinstance(relation_field, ReverseManyToOneDescriptor):
            current_model = relation_field.field.model
            continue
        next_model = getattr(relation_field, "related_model", None)
        if next_model is None:
            remote_field = getattr(relation_field, "remote_field", None)
            next_model = getattr(remote_field, "model", None)
        if not isinstance(next_model, type) or not issubclass(next_model, models.Model):
            raise TypeError(
                f"Response related_list lookup {relation_lookup!r} does not end on a "
                f"Django relation from model {current_model.__name__}."
            )
        current_model = next_model
    return current_model


def model_relation_field_by_name(
    *,
    model: type[models.Model],
    relation_name: str,
) -> Any:
    """Return one forward or reverse relation field by Django lookup name."""
    try:
        return model._meta.get_field(relation_name)
    except FieldDoesNotExist:
        for relation_field in model._meta.get_fields():
            if getattr(relation_field, "name", None) == relation_name:
                return relation_field
    descriptor = getattr(model, relation_name, None)
    if isinstance(descriptor, ReverseManyToOneDescriptor):
        return descriptor
    raise FieldDoesNotExist(f"{model.__name__} has no field named {relation_name!r}.")


def queryset_for_related_prefetch(
    *,
    related_model: type[models.Model],
    declaration: RelatedListDeclaration | None,
    child_prefetches: tuple[models.Prefetch, ...],
) -> models.QuerySet[Any] | None:
    """Return the queryset attached to one Prefetch declaration."""
    queryset: models.QuerySet[Any] | None = None
    if declaration is not None and declaration.queryset is not None:
        queryset = declaration.queryset
        if queryset.model is not related_model:
            raise TypeError(
                f"related_list queryset targets {queryset.model.__name__}, but the "
                f"declared relation resolves to {related_model.__name__}."
            )
    elif declaration is not None or child_prefetches:
        queryset = related_model._default_manager.all()

    if queryset is not None and child_prefetches:
        queryset = queryset.prefetch_related(*child_prefetches)
    return queryset
