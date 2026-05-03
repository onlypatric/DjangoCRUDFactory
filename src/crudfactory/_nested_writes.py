from __future__ import annotations

from dataclasses import Field, dataclass, fields
from typing import Any, Callable, Literal, Sequence, TypeVar, cast, get_args, get_origin, get_type_hints

from django.core.exceptions import FieldDoesNotExist
from django.db import models, transaction
from rest_framework import serializers

from ._simple_writes import (
    MODEL_FIELD_METADATA_KEY,
    WritableFieldMapping,
    dataclass_fields_for_lookup,
    model_field_name_from_metadata,
    resolve_writable_field_mappings,
    save_instance_if_needed,
    set_model_values_from_dto,
    transformed_dto_value,
)
from .dataclass_serializers import ensure_dataclass_type, unwrap_optional_type

NestedWriteMode = Literal["create-only", "replace", "merge"]
MissingMatchBehavior = Literal["create", "error"]

M = TypeVar("M", bound=models.Model)
DTO = TypeVar("DTO")

__all__ = ["NestedWriteSpec", "nested_relation"]


@dataclass(frozen=True)
class NestedWriteSpec:
    """Describe one one-to-many child collection written through the root DTO."""

    field_name: str
    relation_name: str | None = None
    mode: NestedWriteMode = "replace"
    match_by: str | None = None
    on_missing_match: MissingMatchBehavior = "create"


@dataclass(frozen=True)
class ResolvedNestedWriteSpec:
    """Runtime-ready nested write definition for one parent model relation."""

    config: NestedWriteSpec
    relation_name: str
    child_model: type[models.Model]
    parent_fk_field_name: str


@dataclass(frozen=True)
class ActionNestedWriteSpec:
    """Resolved nested write config tied to one concrete action DTO type."""

    resolved_spec: ResolvedNestedWriteSpec
    child_dataclass_type: type[Any]


@dataclass(frozen=True)
class ChildIdentitySpec:
    """How one nested DTO item matches an existing child row."""

    dto_field_name: str
    model_field_name: str
    writable_on_create: bool


def nested_relation(
    *,
    field_name: str,
    relation_name: str | None = None,
    mode: NestedWriteMode = "replace",
    match_by: str | None = None,
    on_missing_match: MissingMatchBehavior = "create",
) -> NestedWriteSpec:
    """Return a nested write configuration for a one-to-many child relation."""
    return NestedWriteSpec(
        field_name=field_name,
        relation_name=relation_name,
        mode=mode,
        match_by=match_by,
        on_missing_match=on_missing_match,
    )


def normalize_nested_writes(
    nested_writes: Sequence[NestedWriteSpec] | None,
) -> tuple[NestedWriteSpec, ...]:
    """Freeze optional nested write specs for stable handler generation."""
    if nested_writes is None:
        return ()
    return tuple(nested_writes)


def nested_field_names(nested_writes: tuple[NestedWriteSpec, ...]) -> frozenset[str]:
    """Return the DTO field names reserved for nested relation writes."""
    return frozenset(spec.field_name for spec in nested_writes)


def resolve_nested_write_specs(
    *,
    model: type[models.Model],
    nested_writes: tuple[NestedWriteSpec, ...],
) -> tuple[ResolvedNestedWriteSpec, ...]:
    """Resolve and validate nested relation targets against the Django model."""
    resolved_specs = tuple(
        resolve_nested_write_spec(model=model, nested_write=nested_write)
        for nested_write in nested_writes
    )
    validate_unique_nested_field_names(resolved_specs)
    validate_unique_nested_relation_names(resolved_specs)
    return resolved_specs


def resolve_nested_write_spec(
    *,
    model: type[models.Model],
    nested_write: NestedWriteSpec,
) -> ResolvedNestedWriteSpec:
    """Resolve one nested relation config to concrete Django relation metadata."""
    validate_non_empty_nested_field_name(nested_write.field_name)
    validate_nested_write_mode(nested_write.mode)
    validate_missing_match_behavior(nested_write.on_missing_match)
    relation_name = nested_write.relation_name or nested_write.field_name
    relation = relation_for_nested_write(model, relation_name)
    child_model = cast(type[models.Model], relation.related_model)
    parent_fk_field_name = relation.field.name
    return ResolvedNestedWriteSpec(
        config=nested_write,
        relation_name=relation_name,
        child_model=child_model,
        parent_fk_field_name=parent_fk_field_name,
    )


def validate_nested_write_dataclass(
    *,
    model: type[models.Model],
    dataclass_type: type[Any],
    nested_writes: tuple[NestedWriteSpec, ...],
    action_name: str,
    partial: bool,
) -> None:
    """Validate one request DTO against configured nested relation writes."""
    if not nested_writes:
        return

    resolved_specs = resolve_nested_write_specs(model=model, nested_writes=nested_writes)
    dataclass_fields_by_name = dataclass_fields_for_lookup(dataclass_type)
    type_hints = get_type_hints(dataclass_type)

    for resolved_spec in resolved_specs:
        dataclass_field = dataclass_fields_by_name.get(resolved_spec.config.field_name)
        if dataclass_field is None:
            continue
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        child_dataclass_type = nested_child_dataclass_from_annotation(
            field_type,
            field_name=dataclass_field.name,
        )
        validate_nested_child_dataclass(
            child_model=resolved_spec.child_model,
            child_dataclass_type=child_dataclass_type,
            resolved_spec=resolved_spec,
            action_name=action_name,
            partial=partial,
        )


def validate_nested_child_dataclass(
    *,
    child_model: type[models.Model],
    child_dataclass_type: type[Any],
    resolved_spec: ResolvedNestedWriteSpec,
    action_name: str,
    partial: bool,
) -> None:
    """Validate one nested child DTO shape for one relation action."""
    ensure_dataclass_type(f"{action_name} nested child", child_dataclass_type)
    if (
        action_name != "create_input"
        and resolved_spec.config.mode in ("replace", "merge")
        and not partial
    ):
        require_child_match_field(
            child_model=child_model,
            child_dataclass_type=child_dataclass_type,
            resolved_spec=resolved_spec,
            action_name=action_name,
        )


def require_child_match_field(
    *,
    child_model: type[models.Model],
    child_dataclass_type: type[Any],
    resolved_spec: ResolvedNestedWriteSpec,
    action_name: str,
) -> None:
    """Require a usable match field on nested full-update DTOs when needed."""
    if resolved_spec.config.match_by is None:
        msg = (
            f"Nested write field {resolved_spec.config.field_name!r} on {action_name} "
            f"requires match_by when mode={resolved_spec.config.mode!r}."
        )
        raise ValueError(msg)
    resolve_child_identity_spec(
        child_model=child_model,
        child_dataclass_type=child_dataclass_type,
        match_by=resolved_spec.config.match_by,
        action_name=action_name,
    )


def relation_for_nested_write(
    model: type[models.Model],
    relation_name: str,
) -> models.ManyToOneRel:
    """Return the one-to-many reverse relation targeted by a nested write."""
    try:
        relation = model._meta.get_field(relation_name)
    except FieldDoesNotExist:
        relation = related_object_by_accessor_name(model, relation_name)
        if relation is None:
            relation = relation_from_model_subclasses(model, relation_name)
            if relation is None:
                msg = f"Nested relation {model.__name__}.{relation_name} does not exist."
                raise ValueError(msg)

    if not isinstance(relation, models.ManyToOneRel):
        msg = (
            f"Nested relation {model.__name__}.{relation_name} must be a reverse "
            "one-to-many relation."
        )
        raise TypeError(msg)
    return relation


def related_object_by_accessor_name(
    model: type[models.Model],
    relation_name: str,
) -> models.ManyToOneRel | None:
    """Return a reverse one-to-many relation by its Django accessor name."""
    for related_object in model._meta.related_objects:
        accessor_name = related_object.get_accessor_name()
        if accessor_name == relation_name and isinstance(related_object, models.ManyToOneRel):
            return related_object
    return None


def relation_from_model_subclasses(
    parent_model: type[models.Model],
    relation_name: str,
) -> models.ManyToOneRel | None:
    """Fallback relation lookup for lightweight test models outside app registry."""
    for candidate_model in all_model_subclasses(models.Model):
        for django_field in candidate_model._meta.get_fields():
            if not isinstance(django_field, models.ForeignKey):
                continue
            if django_field.remote_field.model is not parent_model:
                continue
            accessor_name = django_field.remote_field.get_accessor_name()
            if accessor_name != relation_name:
                continue
            return cast(models.ManyToOneRel, django_field.remote_field)
    return None


def all_model_subclasses(
    root_model: type[models.Model],
) -> list[type[models.Model]]:
    """Return every currently-loaded Django model subclass recursively."""
    subclasses: list[type[models.Model]] = []
    for subclass in root_model.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(all_model_subclasses(subclass))
    return subclasses


def nested_child_dataclass_from_annotation(
    annotation: object,
    *,
    field_name: str,
) -> type[Any]:
    """Return the nested child dataclass type for a `list[ChildDTO]` annotation."""
    inner_type, _ = unwrap_optional_type(annotation)
    origin = get_origin(inner_type)
    if origin is not list:
        msg = f"Nested write field {field_name!r} must be annotated as list[ChildDTO]."
        raise TypeError(msg)
    args = get_args(inner_type)
    if len(args) != 1:
        msg = f"Nested write field {field_name!r} must declare one list child type."
        raise TypeError(msg)
    child_type = args[0]
    if not isinstance(child_type, type):
        msg = f"Nested write field {field_name!r} must use a dataclass child type."
        raise TypeError(msg)
    ensure_dataclass_type(f"nested write field {field_name}", child_type)
    return child_type


def wrap_create_handler_with_nested_writes(
    *,
    model: type[M],
    dataclass_type: type[DTO],
    create_handler: Callable[[DTO], M],
    nested_writes: tuple[NestedWriteSpec, ...],
) -> Callable[[DTO], M]:
    """Return a create handler that persists configured child collections too."""
    action_specs = resolved_action_nested_specs(
        model=model,
        dataclass_type=dataclass_type,
        nested_writes=nested_writes,
    )

    def create_instance(dto: DTO) -> M:
        with transaction.atomic():
            instance = create_handler(dto)
            apply_nested_writes(
                parent_instance=instance,
                dto=dto,
                action_specs=action_specs,
                skip_none_values=False,
                creating_parent=True,
            )
            return instance

    return create_instance


def wrap_update_handler_with_nested_writes(
    *,
    model: type[M],
    dataclass_type: type[DTO],
    update_handler: Callable[[M, DTO], M],
    nested_writes: tuple[NestedWriteSpec, ...],
    partial: bool,
) -> Callable[[M, DTO], M]:
    """Return an update handler that reconciles nested child collections too."""
    action_specs = resolved_action_nested_specs(
        model=model,
        dataclass_type=dataclass_type,
        nested_writes=nested_writes,
    )

    def update_instance(instance: M, dto: DTO) -> M:
        with transaction.atomic():
            updated_instance = update_handler(instance, dto)
            apply_nested_writes(
                parent_instance=updated_instance,
                dto=dto,
                action_specs=action_specs,
                skip_none_values=partial,
                creating_parent=False,
            )
            return updated_instance

    return update_instance


def resolved_action_nested_specs(
    *,
    model: type[models.Model],
    dataclass_type: type[Any],
    nested_writes: tuple[NestedWriteSpec, ...],
) -> tuple[ActionNestedWriteSpec, ...]:
    """Resolve nested relation specs that are present on one action DTO."""
    if not nested_writes:
        return ()
    dataclass_fields_by_name = dataclass_fields_for_lookup(dataclass_type)
    type_hints = get_type_hints(dataclass_type)
    action_specs: list[ActionNestedWriteSpec] = []
    for resolved_spec in resolve_nested_write_specs(model=model, nested_writes=nested_writes):
        dataclass_field = dataclass_fields_by_name.get(resolved_spec.config.field_name)
        if dataclass_field is None:
            continue
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        child_dataclass_type = nested_child_dataclass_from_annotation(
            field_type,
            field_name=dataclass_field.name,
        )
        action_specs.append(
            ActionNestedWriteSpec(
                resolved_spec=resolved_spec,
                child_dataclass_type=child_dataclass_type,
            )
        )
    return tuple(action_specs)


def apply_nested_writes(
    *,
    parent_instance: models.Model,
    dto: object,
    action_specs: tuple[ActionNestedWriteSpec, ...],
    skip_none_values: bool,
    creating_parent: bool,
) -> None:
    """Apply every configured nested collection write for one root DTO."""
    for action_spec in action_specs:
        resolved_spec = action_spec.resolved_spec
        child_items = getattr(dto, resolved_spec.config.field_name)
        if skip_none_values and child_items is None:
            continue
        if child_items is None:
            msg = (
                f"Nested field {resolved_spec.config.field_name!r} cannot be null. "
                "Use an empty list to clear the collection or omit the field in PATCH."
            )
            raise serializers.ValidationError({resolved_spec.config.field_name: [msg]})
        apply_nested_collection_write(
            parent_instance=parent_instance,
            child_items=cast(list[object], child_items),
            action_spec=action_spec,
            skip_none_values=skip_none_values,
            creating_parent=creating_parent,
        )


def apply_nested_collection_write(
    *,
    parent_instance: models.Model,
    child_items: list[object],
    action_spec: ActionNestedWriteSpec,
    skip_none_values: bool,
    creating_parent: bool,
) -> None:
    """Create, update, and optionally delete child rows for one relation."""
    resolved_spec = action_spec.resolved_spec
    manager = getattr(parent_instance, resolved_spec.relation_name)
    if resolved_spec.config.mode == "create-only" or creating_parent:
        create_only_child_rows(
            manager=manager,
            parent_instance=parent_instance,
            child_items=child_items,
            resolved_spec=resolved_spec,
            skip_none_values=skip_none_values,
        )
        return

    identity_spec = require_identity_for_runtime(
        action_spec=action_spec,
    )
    reconcile_child_rows(
        manager=manager,
        parent_instance=parent_instance,
        child_items=child_items,
        resolved_spec=resolved_spec,
        identity_spec=identity_spec,
        skip_none_values=skip_none_values,
    )


def create_only_child_rows(
    *,
    manager: Any,
    parent_instance: models.Model,
    child_items: list[object],
    resolved_spec: ResolvedNestedWriteSpec,
    skip_none_values: bool,
) -> None:
    """Create one child row per nested item without touching existing rows."""
    for child_dto in child_items:
        create_child_row(
            manager=manager,
            parent_instance=parent_instance,
            child_dto=child_dto,
            resolved_spec=resolved_spec,
            identity_spec=None,
            skip_none_values=skip_none_values,
        )


def reconcile_child_rows(
    *,
    manager: Any,
    parent_instance: models.Model,
    child_items: list[object],
    resolved_spec: ResolvedNestedWriteSpec,
    identity_spec: ChildIdentitySpec,
    skip_none_values: bool,
) -> None:
    """Apply merge/replace semantics to one related child collection."""
    child_model = resolved_spec.child_model
    existing_instances = list(manager.all())
    existing_by_key = existing_children_by_key(existing_instances, identity_spec)
    validate_unique_nested_child_keys(child_items, identity_spec, resolved_spec)
    matched_primary_keys: set[object] = set()

    for child_dto in child_items:
        child_key = child_identity_value(child_dto, identity_spec)
        if child_key is None:
            create_child_row(
                manager=manager,
                parent_instance=parent_instance,
                child_dto=child_dto,
                resolved_spec=resolved_spec,
                identity_spec=identity_spec,
                skip_none_values=skip_none_values,
            )
            continue

        existing_instance = existing_by_key.get(child_key)
        if existing_instance is None:
            if resolved_spec.config.on_missing_match == "error":
                raise serializers.ValidationError(
                    {
                        resolved_spec.config.field_name: [
                            f"No existing {child_model.__name__} matches "
                            f"{identity_spec.dto_field_name}={child_key!r}."
                        ]
                    }
                )
            create_child_row(
                manager=manager,
                parent_instance=parent_instance,
                child_dto=child_dto,
                resolved_spec=resolved_spec,
                identity_spec=identity_spec,
                skip_none_values=skip_none_values,
            )
            continue

        update_child_row(
            child_instance=existing_instance,
            child_dto=child_dto,
            resolved_spec=resolved_spec,
            identity_spec=identity_spec,
            skip_none_values=skip_none_values,
        )
        matched_primary_keys.add(existing_instance.pk)

    if resolved_spec.config.mode == "replace":
        delete_unmatched_children(existing_instances, matched_primary_keys)


def create_child_row(
    *,
    manager: Any,
    parent_instance: models.Model,
    child_dto: object,
    resolved_spec: ResolvedNestedWriteSpec,
    identity_spec: ChildIdentitySpec | None,
    skip_none_values: bool,
) -> None:
    """Create one child row from a nested child DTO."""
    mappings = child_writable_mappings(
        child_model=resolved_spec.child_model,
        child_dto=child_dto,
        resolved_spec=resolved_spec,
        action_name="nested_create",
        identity_spec=identity_spec,
    )
    values = child_model_values_from_dto(
        child_dto=child_dto,
        mappings=mappings,
        skip_none_values=skip_none_values,
    )
    if identity_spec is not None and identity_spec.writable_on_create:
        identity_value = child_identity_value(child_dto, identity_spec)
        if identity_value is not None:
            values[identity_spec.model_field_name] = identity_value
    values[resolved_spec.parent_fk_field_name] = parent_instance
    manager.create(**values)


def update_child_row(
    *,
    child_instance: models.Model,
    child_dto: object,
    resolved_spec: ResolvedNestedWriteSpec,
    identity_spec: ChildIdentitySpec,
    skip_none_values: bool,
) -> None:
    """Apply nested DTO values to one existing child row."""
    mappings = child_writable_mappings(
        child_model=resolved_spec.child_model,
        child_dto=child_dto,
        resolved_spec=resolved_spec,
        action_name="nested_update",
        identity_spec=identity_spec,
    )
    updated_fields = set_model_values_from_dto(
        instance=child_instance,
        dto=child_dto,
        mappings=mappings,
        skip_none_values=skip_none_values,
    )
    save_instance_if_needed(child_instance, updated_fields)


def child_writable_mappings(
    *,
    child_model: type[models.Model],
    child_dto: object,
    resolved_spec: ResolvedNestedWriteSpec,
    action_name: str,
    identity_spec: ChildIdentitySpec | None,
) -> tuple[WritableFieldMapping, ...]:
    """Return writable child field mappings, excluding relation control fields."""
    dataclass_type = type(child_dto)
    excluded_fields = {resolved_spec.parent_fk_field_name}
    if identity_spec is not None:
        excluded_fields.add(identity_spec.dto_field_name)
    writable_field_names = tuple(
        dataclass_field.name
        for dataclass_field in fields(cast(Any, dataclass_type))
        if dataclass_field.name not in excluded_fields
    )
    if not writable_field_names:
        return ()
    return resolve_writable_field_mappings(
        model=child_model,
        dataclass_type=dataclass_type,
        writable_fields=writable_field_names,
        action_name=action_name,
    )


def child_model_values_from_dto(
    *,
    child_dto: object,
    mappings: tuple[WritableFieldMapping, ...],
    skip_none_values: bool,
) -> dict[str, object]:
    """Return child model values from a nested DTO and writable mappings."""
    values: dict[str, object] = {}
    for mapping in mappings:
        value = transformed_dto_value(child_dto, mapping)
        if skip_none_values and value is None:
            continue
        values[mapping.model_field_name] = value
    return values


def require_identity_for_runtime(
    *,
    action_spec: ActionNestedWriteSpec,
) -> ChildIdentitySpec:
    """Return the identity spec used to match nested items to child rows."""
    resolved_spec = action_spec.resolved_spec
    if resolved_spec.config.match_by is None:
        msg = (
            f"Nested write field {resolved_spec.config.field_name!r} requires match_by "
            f"when mode={resolved_spec.config.mode!r}."
        )
        raise TypeError(msg)
    return resolve_child_identity_spec(
        child_model=resolved_spec.child_model,
        child_dataclass_type=action_spec.child_dataclass_type,
        match_by=resolved_spec.config.match_by,
        action_name="nested_runtime",
    )


def resolve_child_identity_spec(
    *,
    child_model: type[models.Model],
    child_dataclass_type: type[Any],
    match_by: str,
    action_name: str,
) -> ChildIdentitySpec:
    """Resolve one child DTO field used to match nested items to existing rows."""
    dataclass_fields_by_name = dataclass_fields_for_lookup(child_dataclass_type)
    dataclass_field = dataclass_fields_by_name.get(match_by)
    if dataclass_field is None:
        msg = (
            f"{action_name} nested child DTO {child_dataclass_type.__name__} does not define "
            f"match_by field {match_by!r}."
        )
        raise ValueError(msg)
    model_field_name = model_field_name_from_metadata(dataclass_field)
    validate_identity_field_exists(child_model, model_field_name)
    return ChildIdentitySpec(
        dto_field_name=match_by,
        model_field_name=model_field_name,
        writable_on_create=identity_field_is_writable(child_model, dataclass_field),
    )


def validate_identity_field_exists(
    child_model: type[models.Model],
    model_field_name: str,
) -> None:
    """Ensure the configured child identity model field actually exists."""
    try:
        child_model._meta.get_field(model_field_name)
    except FieldDoesNotExist as exc:
        msg = (
            f"Nested child match field maps to {child_model.__name__}.{model_field_name}, "
            "but that model field does not exist."
        )
        raise ValueError(msg) from exc


def identity_field_is_writable(
    child_model: type[models.Model],
    dataclass_field: Field[Any],
) -> bool:
    """Return True when the child identity field can safely be set on create."""
    django_field = child_model._meta.get_field(model_field_name_from_metadata(dataclass_field))
    if not getattr(django_field, "concrete", False):
        return False
    if getattr(django_field, "auto_created", False):
        return False
    return bool(getattr(django_field, "editable", False))


def child_identity_value(
    child_dto: object,
    identity_spec: ChildIdentitySpec,
) -> object | None:
    """Return the match key value from one nested child DTO item."""
    return getattr(child_dto, identity_spec.dto_field_name)


def existing_children_by_key(
    existing_instances: list[models.Model],
    identity_spec: ChildIdentitySpec,
) -> dict[object, models.Model]:
    """Map existing child rows by their identity value, rejecting duplicates."""
    existing_by_key: dict[object, models.Model] = {}
    for instance in existing_instances:
        key = getattr(instance, identity_spec.model_field_name)
        if key in existing_by_key:
            msg = (
                f"Existing child rows are not unique on {identity_spec.model_field_name!r}. "
                "Nested writes require a stable unique match key."
            )
            raise serializers.ValidationError(msg)
        existing_by_key[key] = instance
    return existing_by_key


def validate_unique_nested_child_keys(
    child_items: list[object],
    identity_spec: ChildIdentitySpec,
    resolved_spec: ResolvedNestedWriteSpec,
) -> None:
    """Reject duplicate child match keys in one nested request payload."""
    seen_keys: set[object] = set()
    for child_dto in child_items:
        key = child_identity_value(child_dto, identity_spec)
        if key is None:
            continue
        if key in seen_keys:
            raise serializers.ValidationError(
                {
                    resolved_spec.config.field_name: [
                        f"Duplicate nested child {identity_spec.dto_field_name}={key!r}."
                    ]
                }
            )
        seen_keys.add(key)


def delete_unmatched_children(
    existing_instances: list[models.Model],
    matched_primary_keys: set[object],
) -> None:
    """Delete existing child rows that were not matched by a replace payload."""
    for instance in existing_instances:
        if instance.pk in matched_primary_keys:
            continue
        instance.delete()


def validate_unique_nested_field_names(
    resolved_specs: tuple[ResolvedNestedWriteSpec, ...],
) -> None:
    """Reject duplicate nested DTO field names in one factory config."""
    seen_field_names: set[str] = set()
    for resolved_spec in resolved_specs:
        field_name = resolved_spec.config.field_name
        if field_name in seen_field_names:
            msg = f"Duplicate nested write field_name {field_name!r}."
            raise ValueError(msg)
        seen_field_names.add(field_name)


def validate_unique_nested_relation_names(
    resolved_specs: tuple[ResolvedNestedWriteSpec, ...],
) -> None:
    """Reject duplicate nested relation targets in one factory config."""
    seen_relation_names: set[str] = set()
    for resolved_spec in resolved_specs:
        relation_name = resolved_spec.relation_name
        if relation_name in seen_relation_names:
            msg = f"Duplicate nested write relation_name {relation_name!r}."
            raise ValueError(msg)
        seen_relation_names.add(relation_name)


def validate_non_empty_nested_field_name(field_name: str) -> None:
    """Reject empty nested DTO field names."""
    if not field_name:
        msg = "nested_relation field_name must be a non-empty string."
        raise ValueError(msg)


def validate_nested_write_mode(mode: str) -> None:
    """Ensure nested write mode is one of the supported V1 strategies."""
    if mode not in {"create-only", "replace", "merge"}:
        msg = "nested_relation mode must be 'create-only', 'replace', or 'merge'."
        raise ValueError(msg)


def validate_missing_match_behavior(on_missing_match: str) -> None:
    """Ensure unknown nested child match keys use a supported behavior."""
    if on_missing_match not in {"create", "error"}:
        msg = "nested_relation on_missing_match must be 'create' or 'error'."
        raise ValueError(msg)
