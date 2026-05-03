from __future__ import annotations

from collections.abc import Iterable
from dataclasses import Field, MISSING, field, fields, is_dataclass, make_dataclass
from types import UnionType
from typing import Any, cast, get_args, get_origin, get_type_hints
from uuid import UUID

from django.db import models

from .annotations import annotation_value_for_path, field_has_annotation
from ._simple_writes import (
    MODEL_FIELD_METADATA_KEY,
    model_field_name_from_metadata,
    read_transform_from_metadata,
)
from .dataclass_serializers import ensure_dataclass_type
from .stats import STAT_METADATA_KEY
from .types import M, ResponseDTO, ResponseMapper

__all__: list[str] = []


def build_auto_response_mapper(
    *,
    model: type[M],
    source_dataclass: type[Any],
) -> ResponseMapper[M, ResponseDTO]:
    """Build a response mapper from an input DTO dataclass.

    Automatic response mode keeps the public response contract close to the
    user's DTOs. The generated response dataclass includes the model primary key
    as `id` unless the DTO already declares an `id` field, then mirrors the
    source dataclass fields and metadata.
    """
    response_dataclass = build_auto_response_dataclass(
        model=model,
        source_dataclass=source_dataclass,
    )
    source_fields = fields_by_name(source_dataclass)

    def auto_response_mapper(instance: M) -> ResponseDTO:
        response_values = values_for_auto_response(
            instance=instance,
            response_dataclass=response_dataclass,
            source_fields=source_fields,
        )
        return response_dataclass(**response_values)

    auto_response_mapper.__name__ = f"{model.__name__.lower()}_auto_response_mapper"
    auto_response_mapper.__qualname__ = auto_response_mapper.__name__
    auto_response_mapper.__annotations__ = {
        "instance": model,
        "return": response_dataclass,
    }
    return auto_response_mapper


def build_declared_response_mapper(
    *,
    model: type[M],
    response_dataclass: type[Any],
) -> ResponseMapper[M, ResponseDTO]:
    """Build a response mapper directly from a declared response dataclass.

    This lets users keep factory modules terse. A declared response dataclass
    plus `model_field(...)` metadata is enough for CRUDFactory to assemble
    nested DTOs, related-object lists, and dict-backed metadata blocks.
    """
    ensure_dataclass_type("response_dataclass", response_dataclass)

    def declared_response_mapper(instance: M) -> ResponseDTO:
        response_values = values_for_declared_response(
            source=instance,
            dataclass_type=response_dataclass,
        )
        return response_dataclass(**response_values)

    declared_response_mapper.__name__ = (
        f"{model.__name__.lower()}_declared_response_mapper"
    )
    declared_response_mapper.__qualname__ = declared_response_mapper.__name__
    declared_response_mapper.__annotations__ = {
        "instance": model,
        "return": response_dataclass,
    }
    return declared_response_mapper


def build_auto_response_dataclass(
    *,
    model: type[models.Model],
    source_dataclass: type[Any],
) -> type[Any]:
    """Create the dataclass used as the generated response contract."""
    ensure_dataclass_type("update_input", source_dataclass)
    type_hints = get_type_hints(source_dataclass)
    dataclass_fields = response_field_definitions(
        model=model,
        source_dataclass=source_dataclass,
        type_hints=type_hints,
    )
    return make_dataclass(
        cls_name=f"{model.__name__}AutoResponseDTO",
        fields=dataclass_fields,
    )


def response_field_definitions(
    *,
    model: type[models.Model],
    source_dataclass: type[Any],
    type_hints: dict[str, Any],
) -> list[tuple[str, Any, Field[Any]]]:
    """Return fields for the generated response dataclass."""
    definitions: list[tuple[str, Any, Field[Any]]] = []
    source_names = {dataclass_field.name for dataclass_field in fields(source_dataclass)}
    if "id" not in source_names:
        definitions.append(auto_id_field_definition(model))

    for dataclass_field in fields(source_dataclass):
        definitions.append(
            (
                dataclass_field.name,
                type_hints.get(dataclass_field.name, dataclass_field.type),
                field(metadata=dict(dataclass_field.metadata)),
            )
        )
    return definitions


def auto_id_field_definition(
    model: type[models.Model],
) -> tuple[str, Any, Field[Any]]:
    """Return the default `id` response field derived from the model primary key."""
    return (
        "id",
        primary_key_python_type(model),
        field(metadata={MODEL_FIELD_METADATA_KEY: "pk"}),
    )


def primary_key_python_type(model: type[models.Model]) -> type[object]:
    """Map common Django primary key fields to supported response types."""
    primary_key = model._meta.pk
    if isinstance(primary_key, models.UUIDField):
        return UUID
    if isinstance(primary_key, models.IntegerField):
        return int
    return str


def fields_by_name(dataclass_type: type[Any]) -> dict[str, Field[Any]]:
    """Return dataclass fields keyed by field name."""
    return {
        dataclass_field.name: dataclass_field
        for dataclass_field in fields(dataclass_type)
    }


def values_for_auto_response(
    *,
    instance: models.Model,
    response_dataclass: type[Any],
    source_fields: dict[str, Field[Any]],
) -> dict[str, object]:
    """Read every generated response field from the model instance."""
    values: dict[str, object] = {}
    for response_field in fields(response_dataclass):
        source_field = source_fields.get(response_field.name, response_field)
        values[response_field.name] = value_for_response_field(instance, source_field)
    return values


def value_for_response_field(instance: models.Model, dataclass_field: Field[Any]) -> object:
    """Read one response value and apply an optional read transform."""
    model_lookup = model_field_name_from_metadata(dataclass_field)
    value = read_model_lookup(instance, model_lookup)
    read_transform = read_transform_from_metadata(dataclass_field)
    if read_transform is None:
        return value
    return read_transform(value)


def values_for_declared_response(
    *,
    source: object,
    dataclass_type: type[Any],
    path: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build one declared response dataclass from a model, dict, or related row."""
    type_hints = get_type_hints(dataclass_type)
    values: dict[str, object] = {}
    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        values[dataclass_field.name] = value_for_declared_response_field(
            source=source,
            dataclass_field=dataclass_field,
            field_type=field_type,
            path=(*path, dataclass_field.name),
        )
    return values


def value_for_declared_response_field(
    *,
    source: object,
    dataclass_field: Field[Any],
    field_type: Any,
    path: tuple[str, ...],
) -> object:
    """Return one declared response field value, recursing when needed."""
    if field_has_annotation(dataclass_field):
        return annotation_value_for_path(
            instance=source,
            dataclass_field=dataclass_field,
            path=path,
        )
    if field_declares_stat(dataclass_field):
        return default_value_for_dataclass_field(dataclass_field)

    nested_dataclass_type = nested_dataclass_type_from_annotation(field_type)
    if nested_dataclass_type is not None:
        nested_source = nested_source_for_field(source, dataclass_field)
        return nested_dataclass_type(
            **values_for_declared_response(
                source=nested_source,
                dataclass_type=nested_dataclass_type,
                path=path,
            )
        )

    list_child_dataclass_type = list_child_dataclass_type_from_annotation(field_type)
    if list_child_dataclass_type is not None:
        iterable_source = iterable_source_for_field(source, dataclass_field)
        return [
            list_child_dataclass_type(
                **values_for_declared_response(
                    source=item,
                    dataclass_type=list_child_dataclass_type,
                    path=path,
                )
            )
            for item in iterable_source
        ]

    value = read_model_lookup(source, model_field_name_from_metadata(dataclass_field))
    read_transform = read_transform_from_metadata(dataclass_field)
    if read_transform is None:
        return value
    return read_transform(value)


def nested_source_for_field(source: object, dataclass_field: Field[Any]) -> object:
    """Return the object used to build one nested response dataclass field."""
    if field_declares_model_lookup(dataclass_field):
        return read_model_lookup(source, model_field_name_from_metadata(dataclass_field))
    return source


def iterable_source_for_field(
    source: object,
    dataclass_field: Field[Any],
) -> list[object]:
    """Normalize a related manager, queryset, or iterable into a plain list."""
    raw_value = read_model_lookup(source, model_field_name_from_metadata(dataclass_field))
    if raw_value is None:
        return []
    all_method = getattr(raw_value, "all", None)
    if callable(all_method):
        return list(cast(Iterable[object], all_method()))
    if isinstance(raw_value, Iterable) and not isinstance(
        raw_value,
        (str, bytes, dict),
    ):
        return list(cast(Iterable[object], raw_value))
    msg = (
        f"Response field {dataclass_field.name!r} expected an iterable source, "
        f"got {type(raw_value).__name__}."
    )
    raise TypeError(msg)


def field_declares_model_lookup(dataclass_field: Field[Any]) -> bool:
    """Return True when a response field overrides its default source lookup."""
    return MODEL_FIELD_METADATA_KEY in dataclass_field.metadata


def field_declares_stat(dataclass_field: Field[Any]) -> bool:
    """Return True when a response field is populated by aggregate annotations."""
    return STAT_METADATA_KEY in dataclass_field.metadata


def default_value_for_dataclass_field(dataclass_field: Field[Any]) -> object:
    """Return the declared default used before stat annotations are applied."""
    if dataclass_field.default is not MISSING:
        return dataclass_field.default
    if dataclass_field.default_factory is not MISSING:
        return dataclass_field.default_factory()
    return None


def nested_dataclass_type_from_annotation(annotation: object) -> type[Any] | None:
    """Return one nested dataclass type for direct or optional annotations."""
    unwrapped_annotation = unwrap_optional_annotation(annotation)
    if isinstance(unwrapped_annotation, type) and is_dataclass(unwrapped_annotation):
        return unwrapped_annotation
    return None


def list_child_dataclass_type_from_annotation(annotation: object) -> type[Any] | None:
    """Return the nested dataclass item type for list annotations, if any."""
    unwrapped_annotation = unwrap_optional_annotation(annotation)
    if get_origin(unwrapped_annotation) is not list:
        return None
    child_args = get_args(unwrapped_annotation)
    if len(child_args) != 1:
        return None
    child_annotation = unwrap_optional_annotation(child_args[0])
    if isinstance(child_annotation, type) and is_dataclass(child_annotation):
        return child_annotation
    return None


def unwrap_optional_annotation(annotation: object) -> object:
    """Return the inner annotation for Optional[T] or T | None."""
    origin = get_origin(annotation)
    if origin not in (UnionType, None) and origin is not None:
        return annotation
    union_args = get_args(annotation)
    if not union_args:
        return annotation
    non_none_args = [argument for argument in union_args if argument is not type(None)]
    if len(non_none_args) == 1 and len(non_none_args) != len(union_args):
        return non_none_args[0]
    return annotation


def read_model_lookup(instance: object, model_lookup: str) -> object:
    """Read a direct, dotted, or Django-style double-underscore attribute path."""
    value: object = instance
    for attribute_name in model_lookup.replace("__", ".").split("."):
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get(attribute_name)
            continue
        value = getattr(value, attribute_name)
    return value
