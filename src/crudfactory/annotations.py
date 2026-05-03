from __future__ import annotations

from dataclasses import Field, fields, is_dataclass
from types import UnionType
from typing import Any, Callable, Union, cast, get_args, get_origin, get_type_hints

from django.db import models
from django.db.models.expressions import BaseExpression

from .filters import response_dataclass_from_mapper
from .types import M

ANNOTATION_METADATA_KEY = "crudfactory_annotation"

__all__ = [
    "AnnotationSpec",
    "annotate_queryset_with_annotation_specs",
    "annotated_field",
    "annotation_alias_for_path",
    "annotation_specs_from_response_mapper",
    "annotation_value_for_path",
    "apply_annotation_values_to_response_data",
    "field_has_annotation",
    "instance_with_annotation_specs",
]


class AnnotationDeclaration:
    """Describe one declarative queryset annotation attached to a response field."""

    def __init__(
        self,
        *,
        annotation: BaseExpression,
        alias: str | None = None,
        default: object = None,
    ) -> None:
        self.annotation = annotation
        self.alias = alias
        self.default = default


class AnnotationSpec:
    """A discovered response field that must be populated from a queryset annotation."""

    def __init__(
        self,
        *,
        path: tuple[str, ...],
        alias: str,
        declaration: AnnotationDeclaration,
    ) -> None:
        self.path = path
        self.alias = alias
        self.declaration = declaration


def annotated_field(
    *,
    annotation: BaseExpression,
    alias: str | None = None,
    default: object = None,
) -> dict[str, object]:
    """Return response-field metadata for one declarative queryset annotation."""
    return {
        ANNOTATION_METADATA_KEY: AnnotationDeclaration(
            annotation=annotation,
            alias=alias,
            default=default,
        )
    }


def annotation_specs_from_response_mapper(
    response_mapper: Callable[..., object],
) -> tuple[AnnotationSpec, ...]:
    """Discover annotation-backed fields anywhere in the response dataclass tree."""
    response_type = response_dataclass_from_mapper(response_mapper)
    if response_type is None:
        return ()
    return tuple(walk_dataclass_annotation_specs(response_type, path=()))


def walk_dataclass_annotation_specs(
    dataclass_type: type[Any],
    *,
    path: tuple[str, ...],
) -> list[AnnotationSpec]:
    """Collect annotation metadata from nested response dataclasses."""
    specs: list[AnnotationSpec] = []
    type_hints = get_type_hints(dataclass_type)
    for dataclass_field in fields(dataclass_type):
        field_path = (*path, dataclass_field.name)
        if field_has_annotation(dataclass_field):
            specs.append(annotation_spec_from_field(dataclass_field, field_path))

        nested_dataclass_type = dataclass_type_from_annotation(
            type_hints.get(dataclass_field.name, dataclass_field.type)
        )
        if nested_dataclass_type is not None:
            specs.extend(walk_dataclass_annotation_specs(nested_dataclass_type, path=field_path))
    return specs


def annotation_spec_from_field(
    dataclass_field: Field[Any],
    path: tuple[str, ...],
) -> AnnotationSpec:
    """Convert one annotation-backed dataclass field into a discovered spec."""
    metadata_value = dataclass_field.metadata[ANNOTATION_METADATA_KEY]
    if not isinstance(metadata_value, AnnotationDeclaration):
        msg = (
            f"Invalid annotation metadata for {'.'.join(path)!r}. "
            "Use annotated_field(annotation=...)."
        )
        raise TypeError(msg)
    if not isinstance(metadata_value.annotation, BaseExpression):
        msg = (
            f"Invalid annotation expression for {'.'.join(path)!r}. "
            "annotated_field() requires a Django expression such as Subquery(), Exists(), or Case()."
        )
        raise TypeError(msg)
    return AnnotationSpec(
        path=path,
        alias=annotation_alias_for_path(path),
        declaration=metadata_value,
    )


def annotation_alias_for_path(path: tuple[str, ...]) -> str:
    """Return a stable private queryset annotation alias for one response field path."""
    return "_crudfactory_annotation__" + "__".join(path)


def annotate_queryset_with_annotation_specs(
    queryset: models.QuerySet[M],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> models.QuerySet[M]:
    """Add all declarative field annotations to a queryset."""
    if not annotation_specs:
        return queryset
    annotations = {
        annotation_spec.alias: annotation_spec.declaration.annotation
        for annotation_spec in annotation_specs
    }
    return queryset.annotate(**annotations)


def instance_with_annotation_specs(
    *,
    instance: M,
    queryset: models.QuerySet[M],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> M:
    """Return a fresh instance carrying configured declarative annotations."""
    if not annotation_specs:
        return instance
    primary_key = instance.pk
    if primary_key is None:
        return instance
    annotated_queryset = annotate_queryset_with_annotation_specs(queryset, annotation_specs)
    annotated_instance = annotated_queryset.filter(pk=primary_key).first()
    if annotated_instance is None:
        return instance
    return cast(M, annotated_instance)


def apply_annotation_values_to_response_data(
    *,
    data: dict[str, Any],
    instance: models.Model,
    annotation_specs: tuple[AnnotationSpec, ...],
) -> dict[str, Any]:
    """Inject annotation-backed scalar values into nested response payloads."""
    for annotation_spec in annotation_specs:
        if not hasattr(instance, annotation_spec.alias):
            continue
        set_nested_response_value(
            data=data,
            path=annotation_spec.path,
            value=getattr(instance, annotation_spec.alias),
        )
    return data


def set_nested_response_value(
    *,
    data: dict[str, Any],
    path: tuple[str, ...],
    value: object,
) -> None:
    """Set one nested key inside response data, creating dict parents as needed."""
    current: dict[str, Any] = data
    for key in path[:-1]:
        nested = current.get(key)
        if not isinstance(nested, dict):
            nested = {}
            current[key] = nested
        current = nested
    current[path[-1]] = value


def field_has_annotation(dataclass_field: Field[Any]) -> bool:
    """Return True when a response field is populated by a declarative annotation."""
    return ANNOTATION_METADATA_KEY in dataclass_field.metadata


def annotation_value_for_path(
    *,
    instance: object,
    dataclass_field: Field[Any],
    path: tuple[str, ...],
) -> object:
    """Return the annotated scalar value or the declared field default."""
    metadata_value = dataclass_field.metadata[ANNOTATION_METADATA_KEY]
    if not isinstance(metadata_value, AnnotationDeclaration):
        msg = (
            f"Invalid annotation metadata for {dataclass_field.name!r}. "
            "Use annotated_field(annotation=...)."
        )
        raise TypeError(msg)
    alias = annotation_alias_for_path(path)
    if hasattr(instance, alias):
        return getattr(instance, alias)
    return metadata_value.default


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
