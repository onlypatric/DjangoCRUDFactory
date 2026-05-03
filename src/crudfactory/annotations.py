from __future__ import annotations

from dataclasses import Field, fields, is_dataclass
from types import UnionType
from typing import Any, Callable, Union, cast, get_args, get_origin, get_type_hints

from django.db import models
from django.db.models.expressions import BaseExpression
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.db.models.query import QuerySet
from django.db.models import OuterRef, Subquery

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
    "latest_related_value",
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


class LatestRelatedDeclaration:
    """Describe one scalar pulled from the latest related child row."""

    def __init__(
        self,
        *,
        value_field: str,
        order_by: str | tuple[str, ...],
        relation: str | None = None,
        model: type[models.Model] | None = None,
        fk_field: str | None = None,
        outer_lookup: str = "pk",
        alias: str | None = None,
        default: object = None,
    ) -> None:
        self.value_field = value_field
        self.order_by = normalize_order_by(order_by)
        self.relation = relation
        self.model = model
        self.fk_field = fk_field
        self.outer_lookup = outer_lookup
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


def latest_related_value(
    *,
    value_field: str,
    order_by: str | tuple[str, ...],
    relation: str | None = None,
    model: type[models.Model] | None = None,
    fk_field: str | None = None,
    outer_lookup: str = "pk",
    alias: str | None = None,
    default: object = None,
) -> dict[str, object]:
    """Return response-field metadata for a latest-related scalar value.

    Example:

    ```python
    latest_value: float | None = field(
        metadata=latest_related_value(
            relation="history_values",
            value_field="value",
            order_by="-recorded_at",
        )
    )
    ```
    """
    return {
        ANNOTATION_METADATA_KEY: LatestRelatedDeclaration(
            value_field=value_field,
            order_by=order_by,
            relation=relation,
            model=model,
            fk_field=fk_field,
            outer_lookup=outer_lookup,
            alias=alias,
            default=default,
        )
    }


def annotation_specs_from_response_mapper(
    model: type[models.Model],
    response_mapper: Callable[..., object],
) -> tuple[AnnotationSpec, ...]:
    """Discover annotation-backed fields anywhere in the response dataclass tree."""
    response_type = response_dataclass_from_mapper(response_mapper)
    if response_type is None:
        return ()
    return tuple(
        walk_dataclass_annotation_specs(
            model=model,
            dataclass_type=response_type,
            path=(),
        )
    )


def walk_dataclass_annotation_specs(
    *,
    model: type[models.Model],
    dataclass_type: type[Any],
    path: tuple[str, ...],
) -> list[AnnotationSpec]:
    """Collect annotation metadata from nested response dataclasses."""
    specs: list[AnnotationSpec] = []
    type_hints = get_type_hints(dataclass_type)
    for dataclass_field in fields(dataclass_type):
        field_path = (*path, dataclass_field.name)
        if field_has_annotation(dataclass_field):
            specs.append(annotation_spec_from_field(model, dataclass_field, field_path))

        nested_dataclass_type = dataclass_type_from_annotation(
            type_hints.get(dataclass_field.name, dataclass_field.type)
        )
        if nested_dataclass_type is not None:
            specs.extend(
                walk_dataclass_annotation_specs(
                    model=model,
                    dataclass_type=nested_dataclass_type,
                    path=field_path,
                )
            )
    return specs


def annotation_spec_from_field(
    model: type[models.Model],
    dataclass_field: Field[Any],
    path: tuple[str, ...],
) -> AnnotationSpec:
    """Convert one annotation-backed dataclass field into a discovered spec."""
    metadata_value = dataclass_field.metadata[ANNOTATION_METADATA_KEY]
    if not isinstance(metadata_value, (AnnotationDeclaration, LatestRelatedDeclaration)):
        msg = (
            f"Invalid annotation metadata for {'.'.join(path)!r}. "
            "Use annotated_field(...) or latest_related_value(...)."
        )
        raise TypeError(msg)
    declaration = resolved_annotation_declaration(model=model, declaration=metadata_value)
    return AnnotationSpec(
        path=path,
        alias=annotation_alias_for_path(path),
        declaration=declaration,
    )


def resolved_annotation_declaration(
    *,
    model: type[models.Model],
    declaration: AnnotationDeclaration | LatestRelatedDeclaration,
) -> AnnotationDeclaration:
    """Return a concrete annotation declaration for standard or latest-related metadata."""
    if isinstance(declaration, AnnotationDeclaration):
        if not isinstance(declaration.annotation, BaseExpression):
            msg = (
                "Invalid annotation expression. "
                "annotated_field() requires a Django expression such as Subquery(), Exists(), or Case()."
            )
            raise TypeError(msg)
        return declaration
    return AnnotationDeclaration(
        annotation=latest_related_subquery(model=model, declaration=declaration),
        alias=declaration.alias,
        default=declaration.default,
    )


def annotation_alias_for_path(path: tuple[str, ...]) -> str:
    """Return a stable private queryset annotation alias for one response field path."""
    return "_crudfactory_annotation__" + "__".join(path)


def latest_related_subquery(
    *,
    model: type[models.Model],
    declaration: LatestRelatedDeclaration,
) -> BaseExpression:
    """Build the correlated subquery for one latest-related field declaration."""
    related_model, fk_field = resolve_latest_related_model_and_fk(
        model=model,
        declaration=declaration,
    )
    queryset = latest_related_queryset(
        related_model=related_model,
        fk_field=fk_field,
        outer_lookup=declaration.outer_lookup,
        order_by=declaration.order_by,
        value_field=declaration.value_field,
    )
    return Subquery(queryset)


def resolve_latest_related_model_and_fk(
    *,
    model: type[models.Model],
    declaration: LatestRelatedDeclaration,
) -> tuple[type[models.Model], str]:
    """Resolve the child model and FK field for a latest-related declaration."""
    if declaration.relation is not None:
        related_field = next(
            (
                field
                for field in model._meta.get_fields()
                if getattr(field, "name", None) == declaration.relation
            ),
            None,
        )
        if related_field is None:
            msg = (
                f"latest_related_value relation {declaration.relation!r} does not exist "
                f"on {model.__name__}."
            )
            raise TypeError(msg)
        if not isinstance(related_field, ForeignObjectRel):
            msg = (
                f"latest_related_value relation {declaration.relation!r} on "
                f"{model.__name__} must be a reverse relation."
            )
            raise TypeError(msg)
        return cast(type[models.Model], related_field.related_model), related_field.field.name
    if declaration.model is None or declaration.fk_field is None:
        msg = (
            "latest_related_value requires either relation=... or both model=... "
            "and fk_field=...."
        )
        raise TypeError(msg)
    return declaration.model, declaration.fk_field


def latest_related_queryset(
    *,
    related_model: type[models.Model],
    fk_field: str,
    outer_lookup: str,
    order_by: tuple[str, ...],
    value_field: str,
) -> QuerySet[Any]:
    """Return the values queryset used by one latest-related subquery."""
    manager = related_model._default_manager
    filter_kwargs = {fk_field: OuterRef(outer_lookup)}
    return manager.filter(**filter_kwargs).order_by(*order_by).values(value_field)[:1]


def normalize_order_by(order_by: str | tuple[str, ...]) -> tuple[str, ...]:
    """Normalize one or more ordering fields for latest-related declarations."""
    if isinstance(order_by, str):
        return (order_by,)
    return order_by


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
    if not isinstance(metadata_value, (AnnotationDeclaration, LatestRelatedDeclaration)):
        msg = (
            f"Invalid annotation metadata for {dataclass_field.name!r}. "
            "Use annotated_field(...) or latest_related_value(...)."
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
