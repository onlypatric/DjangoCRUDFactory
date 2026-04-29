from __future__ import annotations

from dataclasses import Field, fields
from typing import Any, Callable, Sequence, TypeVar, cast

from django.core.exceptions import FieldDoesNotExist
from django.db import models

from .dataclass_serializers import ensure_dataclass_type

M = TypeVar("M", bound=models.Model)
DTO = TypeVar("DTO")

MODEL_FIELD_METADATA_KEY = "crudfactory_model_field"
MODEL_READ_TRANSFORM_METADATA_KEY = "crudfactory_model_read_transform"
MODEL_WRITE_TRANSFORM_METADATA_KEY = "crudfactory_model_write_transform"

__all__ = ["model_field"]


class WritableFieldMapping:
    """A validated mapping from one DTO field to one model field."""

    def __init__(
        self,
        *,
        dto_field_name: str,
        model_field_name: str,
        write_transform: Callable[[Any], Any] | None,
    ) -> None:
        self.dto_field_name = dto_field_name
        self.model_field_name = model_field_name
        self.write_transform = write_transform


def model_field(
    field_name: str,
    *,
    read_transform: Callable[[Any], Any] | None = None,
    write_transform: Callable[[Any], Any] | None = None,
) -> dict[str, object]:
    """Return metadata that maps a DTO field to a different model field.

    Most simple CRUD DTO fields can use the same name as their Django model
    field.  Use this helper only when the public API name should differ from
    the database/model name:

    ```python
    public_name: str = field(metadata=model_field("name"))
    ```
    """
    if not field_name:
        msg = "model_field requires a non-empty Django model field name."
        raise ValueError(msg)
    metadata: dict[str, object] = {MODEL_FIELD_METADATA_KEY: field_name}
    if read_transform is not None:
        validate_transform_callable("read_transform", read_transform)
        metadata[MODEL_READ_TRANSFORM_METADATA_KEY] = read_transform
    if write_transform is not None:
        validate_transform_callable("write_transform", write_transform)
        metadata[MODEL_WRITE_TRANSFORM_METADATA_KEY] = write_transform
    return metadata


def build_simple_create_handler(
    *,
    model: type[M],
    dataclass_type: type[DTO],
    writable_fields: Sequence[str],
) -> CallableCreateHandler[DTO, M]:
    """Build a create handler that writes allowed DTO fields to the model."""
    mappings = resolve_writable_field_mappings(
        model=model,
        dataclass_type=dataclass_type,
        writable_fields=writable_fields,
        action_name="create",
    )

    def create_instance(dto: DTO) -> M:
        values = model_values_from_dto(dto, mappings)
        return cast(M, model._default_manager.create(**values))

    return create_instance


def build_simple_update_handler(
    *,
    model: type[M],
    dataclass_type: type[DTO],
    writable_fields: Sequence[str],
) -> CallableUpdateHandler[M, DTO]:
    """Build an update handler that writes every allowed DTO field."""
    mappings = resolve_writable_field_mappings(
        model=model,
        dataclass_type=dataclass_type,
        writable_fields=writable_fields,
        action_name="update",
    )

    def update_instance(instance: M, dto: DTO) -> M:
        updated_model_fields = set_model_values_from_dto(
            instance=instance,
            dto=dto,
            mappings=mappings,
            skip_none_values=False,
        )
        save_instance_if_needed(instance, updated_model_fields)
        return instance

    return update_instance


def build_simple_partial_update_handler(
    *,
    model: type[M],
    dataclass_type: type[DTO],
    writable_fields: Sequence[str],
) -> CallableUpdateHandler[M, DTO]:
    """Build a PATCH handler that writes only non-None DTO values.

    CRUDFactory normalizes omitted optional PATCH fields to `None`.  Treating
    `None` as "not provided" keeps simple partial updates predictable, but it
    also means this helper does not support patching a nullable model field to
    SQL NULL.  Use explicit handlers for that case.
    """
    mappings = resolve_writable_field_mappings(
        model=model,
        dataclass_type=dataclass_type,
        writable_fields=writable_fields,
        action_name="partial_update",
    )

    def patch_instance(instance: M, dto: DTO) -> M:
        updated_model_fields = set_model_values_from_dto(
            instance=instance,
            dto=dto,
            mappings=mappings,
            skip_none_values=True,
        )
        save_instance_if_needed(instance, updated_model_fields)
        return instance

    return patch_instance


def writable_field_names_from_dataclass(dataclass_type: type[Any]) -> tuple[str, ...]:
    """Return every DTO field name as the generated write allowlist."""
    ensure_dataclass_type("input dataclass", dataclass_type)
    return tuple(dataclass_field.name for dataclass_field in fields(dataclass_type))


def resolve_writable_field_mappings(
    *,
    model: type[models.Model],
    dataclass_type: type[Any],
    writable_fields: Sequence[str],
    action_name: str,
) -> tuple[WritableFieldMapping, ...]:
    """Validate and resolve every configured writable DTO field."""
    ensure_dataclass_type(f"{action_name}_input", dataclass_type)
    validate_writable_fields_are_configured(writable_fields)

    dataclass_fields_by_name = dataclass_fields_for_lookup(dataclass_type)
    mappings = tuple(
        mapping_for_writable_field(
            model=model,
            dataclass_fields_by_name=dataclass_fields_by_name,
            dto_field_name=dto_field_name,
            action_name=action_name,
        )
        for dto_field_name in writable_fields
    )
    validate_unique_model_targets(mappings)
    return mappings


def validate_writable_fields_are_configured(writable_fields: Sequence[str]) -> None:
    """Fail early when simple writes do not have an allowlist."""
    if not writable_fields:
        msg = "writable_fields must include at least one DTO field name."
        raise ValueError(msg)
    for field_name in writable_fields:
        if not field_name:
            msg = "writable_fields cannot contain empty field names."
            raise ValueError(msg)


def dataclass_fields_for_lookup(
    dataclass_type: type[Any],
) -> dict[str, Field[Any]]:
    """Return dataclass fields keyed by their public DTO field name."""
    return {dataclass_field.name: dataclass_field for dataclass_field in fields(dataclass_type)}


def mapping_for_writable_field(
    *,
    model: type[models.Model],
    dataclass_fields_by_name: dict[str, Field[Any]],
    dto_field_name: str,
    action_name: str,
) -> WritableFieldMapping:
    """Resolve one public DTO field name to one concrete model field name."""
    dataclass_field = dataclass_fields_by_name.get(dto_field_name)
    if dataclass_field is None:
        msg = (
            f"writable_fields contains {dto_field_name!r}, but {action_name}_input "
            "does not define that DTO field."
        )
        raise ValueError(msg)

    model_field_name = model_field_name_from_metadata(dataclass_field)
    validate_model_field_can_be_written(model, model_field_name)
    return WritableFieldMapping(
        dto_field_name=dto_field_name,
        model_field_name=model_field_name,
        write_transform=write_transform_from_metadata(dataclass_field),
    )


def model_field_name_from_metadata(dataclass_field: Field[Any]) -> str:
    """Return the mapped model field name for one DTO field."""
    raw_model_field_name = dataclass_field.metadata.get(MODEL_FIELD_METADATA_KEY)
    if raw_model_field_name is None:
        return dataclass_field.name
    if isinstance(raw_model_field_name, str) and raw_model_field_name:
        return raw_model_field_name
    msg = (
        f"Invalid model_field metadata on DTO field {dataclass_field.name!r}. "
        "Use model_field('django_model_field_name')."
    )
    raise TypeError(msg)


def read_transform_from_metadata(
    dataclass_field: Field[Any],
) -> Callable[[Any], Any] | None:
    """Return the optional model-to-API transform for one DTO field."""
    return optional_transform_from_metadata(
        dataclass_field=dataclass_field,
        metadata_key=MODEL_READ_TRANSFORM_METADATA_KEY,
        transform_name="read_transform",
    )


def write_transform_from_metadata(
    dataclass_field: Field[Any],
) -> Callable[[Any], Any] | None:
    """Return the optional API-to-model transform for one DTO field."""
    return optional_transform_from_metadata(
        dataclass_field=dataclass_field,
        metadata_key=MODEL_WRITE_TRANSFORM_METADATA_KEY,
        transform_name="write_transform",
    )


def optional_transform_from_metadata(
    *,
    dataclass_field: Field[Any],
    metadata_key: str,
    transform_name: str,
) -> Callable[[Any], Any] | None:
    """Validate and return one optional transform callable from metadata."""
    transform = dataclass_field.metadata.get(metadata_key)
    if transform is None:
        return None
    validate_transform_callable(transform_name, transform)
    return transform


def validate_transform_callable(name: str, value: object) -> None:
    """Ensure custom field transforms can be called by generated code."""
    if not callable(value):
        msg = f"model_field {name} must be callable."
        raise TypeError(msg)


def validate_model_field_can_be_written(
    model: type[models.Model],
    model_field_name: str,
) -> None:
    """Ensure simple writes target a direct, concrete Django model field."""
    try:
        django_field = model._meta.get_field(model_field_name)
    except FieldDoesNotExist as exc:
        msg = (
            f"writable_fields maps to {model.__name__}.{model_field_name}, "
            "but that model field does not exist."
        )
        raise ValueError(msg) from exc

    if not field_is_simple_writable_model_field(django_field):
        msg = (
            f"writable_fields maps to {model.__name__}.{model_field_name}, "
            "but simple writes only support direct editable concrete model fields."
        )
        raise TypeError(msg)


def field_is_simple_writable_model_field(django_field: Any) -> bool:
    """Return True for model fields safe enough for generated assignment."""
    if not getattr(django_field, "concrete", False):
        return False
    if getattr(django_field, "auto_created", False):
        return False
    if not getattr(django_field, "editable", False):
        return False
    return not getattr(django_field, "many_to_many", False)


def validate_unique_model_targets(mappings: tuple[WritableFieldMapping, ...]) -> None:
    """Reject ambiguous DTO contracts that write one model field twice."""
    seen_model_fields: dict[str, str] = {}
    for mapping in mappings:
        previous_dto_field = seen_model_fields.get(mapping.model_field_name)
        if previous_dto_field is not None:
            msg = (
                f"DTO fields {previous_dto_field!r} and {mapping.dto_field_name!r} "
                f"both map to model field {mapping.model_field_name!r}."
            )
            raise ValueError(msg)
        seen_model_fields[mapping.model_field_name] = mapping.dto_field_name


def model_values_from_dto(
    dto: object,
    mappings: tuple[WritableFieldMapping, ...],
) -> dict[str, object]:
    """Return model keyword arguments from a DTO and validated mappings."""
    return {
        mapping.model_field_name: transformed_dto_value(dto, mapping)
        for mapping in mappings
    }


def set_model_values_from_dto(
    *,
    instance: models.Model,
    dto: object,
    mappings: tuple[WritableFieldMapping, ...],
    skip_none_values: bool,
) -> list[str]:
    """Apply mapped DTO values to an instance and return touched model fields."""
    updated_model_fields: list[str] = []
    for mapping in mappings:
        value = transformed_dto_value(dto, mapping)
        if skip_none_values and value is None:
            continue
        setattr(instance, mapping.model_field_name, value)
        updated_model_fields.append(mapping.model_field_name)
    return updated_model_fields


def transformed_dto_value(dto: object, mapping: WritableFieldMapping) -> object:
    """Return a DTO value after applying any configured write transform."""
    value = getattr(dto, mapping.dto_field_name)
    if mapping.write_transform is None:
        return value
    return mapping.write_transform(value)


def save_instance_if_needed(instance: models.Model, update_fields: list[str]) -> None:
    """Save an instance only when at least one simple field changed."""
    if update_fields:
        instance.save(update_fields=update_fields)


CallableCreateHandler = Callable[[DTO], M]
CallableUpdateHandler = Callable[[M, DTO], M]
