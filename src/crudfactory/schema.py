from __future__ import annotations

import datetime as dt
from dataclasses import Field, MISSING, fields, is_dataclass
from decimal import Decimal
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from django.db import models
from rest_framework import serializers
from rest_framework.viewsets import ModelViewSet

from .actions import CustomActionSpec
from .bulk_actions import BulkActionSpec
from .dataclass_serializers import (
    build_serializer_fields,
    ensure_dataclass_type,
    first_type_argument_or_any,
    unwrap_optional_type,
)
from .field_subresources import FieldSubresourceSpec, direct_model_field
from .filters import FilterSpec
from .ordering import ORDERING_QUERY_PARAM, OrderSpec
from .source_queries import source_filter_specs_from_dataclass, source_order_specs_from_dataclass

__all__: list[str] = []

_RESPONSE_SERIALIZER_CACHE: dict[
    tuple[type[Any], str],
    type[serializers.Serializer],
] = {}


def build_response_serializer_from_dataclass(
    dataclass_type: type[Any],
    *,
    name: str,
) -> type[serializers.Serializer]:
    """Create a read-only DRF Serializer class from a response dataclass.

    Request serializers deliberately reject nested dataclasses because incoming
    writes should be explicit DTOs.  Response schemas need nested dataclass
    support because output DTOs often contain aggregate stats or grouped data.
    """
    ensure_dataclass_type("response dataclass", dataclass_type)
    cache_key = (dataclass_type, name)
    cached_serializer = _RESPONSE_SERIALIZER_CACHE.get(cache_key)
    if cached_serializer is not None:
        return cached_serializer

    serializer_fields = build_response_serializer_fields(dataclass_type)
    serializer_class = type(name, (serializers.Serializer,), serializer_fields)
    _RESPONSE_SERIALIZER_CACHE[cache_key] = serializer_class
    return serializer_class


def build_response_serializer_fields(
    dataclass_type: type[Any],
) -> dict[str, serializers.Field]:
    """Return read-only serializer fields for every response dataclass field."""
    serializer_fields: dict[str, serializers.Field] = {}
    type_hints = get_type_hints(dataclass_type)

    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        serializer_fields[dataclass_field.name] = build_response_serializer_field(
            field_type,
            dataclass_field.name,
            dataclass_field=dataclass_field,
        )

    return serializer_fields


def build_response_serializer_field(
    field_type: Any,
    field_name: str,
    *,
    dataclass_field: Field[Any] | None = None,
) -> serializers.Field:
    """Build one read-only DRF field for a response dataclass annotation."""
    inner_type, allow_null = unwrap_optional_type(field_type)
    origin = get_origin(inner_type)
    kwargs = response_field_kwargs(allow_null=allow_null)

    if inner_type is str:
        return serializers.CharField(**kwargs)
    if inner_type is int:
        return serializers.IntegerField(**kwargs)
    if inner_type is float:
        return serializers.FloatField(**kwargs)
    if inner_type is bool:
        return serializers.BooleanField(**kwargs)
    if inner_type is dt.date:
        return serializers.DateField(**kwargs)
    if inner_type is dt.datetime:
        return serializers.DateTimeField(**kwargs)
    if inner_type is Decimal:
        return serializers.DecimalField(max_digits=38, decimal_places=18, **kwargs)
    if inner_type is UUID:
        return serializers.UUIDField(**kwargs)
    if is_dataclass_type(inner_type):
        serializer_class = nested_response_serializer_class(inner_type, field_name)
        return serializer_class(**kwargs)
    if origin is list:
        child_field = build_response_list_child_field(inner_type, field_name)
        return serializers.ListField(child=child_field, **kwargs)

    raise_unsupported_response_field_type(field_name, inner_type, dataclass_field)
    raise AssertionError("raise_unsupported_response_field_type should always raise.")


def build_response_list_child_field(
    list_type: Any,
    field_name: str,
) -> serializers.Field:
    """Build a response ListField child, including nested dataclass children."""
    child_type = first_type_argument_or_any(list_type)
    inner_type, allow_null = unwrap_optional_type(child_type)
    if allow_null:
        msg = f"List response field {field_name!r} cannot use optional child values."
        raise TypeError(msg)
    if is_dataclass_type(inner_type):
        serializer_class = nested_response_serializer_class(inner_type, field_name)
        return serializer_class(read_only=True)
    if get_origin(inner_type) is not None:
        msg = f"Nested list response field {field_name!r} is not supported."
        raise TypeError(msg)
    return build_response_serializer_field(inner_type, field_name)


def nested_response_serializer_class(
    dataclass_type: type[Any],
    field_name: str,
) -> type[serializers.Serializer]:
    """Return a named serializer for one nested response dataclass."""
    serializer_name = f"{dataclass_type.__name__}Serializer"
    return build_response_serializer_from_dataclass(
        dataclass_type,
        name=serializer_name or f"{field_name.title()}ResponseSerializer",
    )


def response_field_kwargs(*, allow_null: bool) -> dict[str, Any]:
    """Return keyword arguments shared by generated response fields."""
    return {"read_only": True, "required": False, "allow_null": allow_null}


def is_dataclass_type(value: object) -> bool:
    """Return True when a type annotation points at a dataclass class."""
    return isinstance(value, type) and is_dataclass(value)


def validate_supported_response_dataclass_fields(dataclass_type: type[Any]) -> None:
    """Validate that every response dataclass field can be represented in schema."""
    ensure_dataclass_type("response dataclass", dataclass_type)
    build_response_serializer_fields(dataclass_type)


def raise_unsupported_response_field_type(
    field_name: str,
    field_type: Any,
    dataclass_field: Field[Any] | None,
) -> None:
    """Raise a consistent error for unsupported response DTO field types."""
    field_label = field_name
    if dataclass_field is not None:
        field_label = dataclass_field.name
    msg = (
        f"Unsupported response field type for {field_label!r}: {field_type!r}. "
        "Supported response types are str, int, float, bool, date, datetime, "
        "Decimal, UUID, Optional[T], list[T], and nested dataclasses."
    )
    raise TypeError(msg)


def apply_schema_metadata(
    viewset_class: type[ModelViewSet],
    *,
    model: type[models.Model],
    response_serializer: type[serializers.Serializer],
    create_serializer: type[serializers.Serializer],
    update_serializer: type[serializers.Serializer],
    patch_serializer: type[serializers.Serializer],
    read_only: bool,
    filter_specs: tuple[FilterSpec, ...],
    order_specs: tuple[OrderSpec, ...],
    list_query: type[object] | None = None,
    custom_actions: tuple[CustomActionSpec[Any], ...] = (),
    custom_action_serializers: dict[str, type[serializers.Serializer]] | None = None,
    custom_action_response_serializers: dict[str, type[serializers.Serializer]] | None = None,
    grouped_actions: tuple[Any, ...] = (),
    grouped_action_serializers: dict[str, type[serializers.Serializer]] | None = None,
    grouped_action_response_serializers: dict[str, type[serializers.Serializer]] | None = None,
    bulk_actions: tuple[BulkActionSpec[Any], ...] = (),
    bulk_action_serializers: dict[str, type[serializers.Serializer]] | None = None,
    bulk_action_response_serializers: dict[str, type[serializers.Serializer]] | None = None,
    field_subresources: tuple[FieldSubresourceSpec, ...] = (),
) -> None:
    """Attach serializer metadata useful to DRF and optional schema tools."""
    setattr(viewset_class, "response_serializer_class", response_serializer)
    setattr(
        viewset_class,
        "request_serializer_classes",
        request_serializers_for_mode(
            create_serializer=create_serializer,
            update_serializer=update_serializer,
            patch_serializer=patch_serializer,
            read_only=read_only,
        ),
    )
    apply_drf_spectacular_metadata(
        viewset_class,
        model=model,
        response_serializer=response_serializer,
        create_serializer=create_serializer,
        update_serializer=update_serializer,
        patch_serializer=patch_serializer,
        read_only=read_only,
        filter_specs=filter_specs,
        order_specs=order_specs,
        list_query=list_query,
        custom_actions=custom_actions,
        custom_action_serializers=custom_action_serializers or {},
        custom_action_response_serializers=custom_action_response_serializers or {},
        grouped_actions=grouped_actions,
        grouped_action_serializers=grouped_action_serializers or {},
        grouped_action_response_serializers=grouped_action_response_serializers or {},
        bulk_actions=bulk_actions,
        bulk_action_serializers=bulk_action_serializers or {},
        bulk_action_response_serializers=bulk_action_response_serializers or {},
        field_subresources=field_subresources,
    )


def request_serializers_for_mode(
    *,
    create_serializer: type[serializers.Serializer],
    update_serializer: type[serializers.Serializer],
    patch_serializer: type[serializers.Serializer],
    read_only: bool,
) -> dict[str, type[serializers.Serializer]]:
    """Return action-specific request serializer metadata."""
    if read_only:
        return {}
    return {
        "create": create_serializer,
        "update": update_serializer,
        "partial_update": patch_serializer,
    }


def apply_drf_spectacular_metadata(
    viewset_class: type[ModelViewSet],
    *,
    model: type[models.Model],
    response_serializer: type[serializers.Serializer],
    create_serializer: type[serializers.Serializer],
    update_serializer: type[serializers.Serializer],
    patch_serializer: type[serializers.Serializer],
    read_only: bool,
    filter_specs: tuple[FilterSpec, ...],
    order_specs: tuple[OrderSpec, ...],
    list_query: type[object] | None,
    custom_actions: tuple[CustomActionSpec[Any], ...],
    custom_action_serializers: dict[str, type[serializers.Serializer]],
    custom_action_response_serializers: dict[str, type[serializers.Serializer]],
    grouped_actions: tuple[Any, ...],
    grouped_action_serializers: dict[str, type[serializers.Serializer]],
    grouped_action_response_serializers: dict[str, type[serializers.Serializer]],
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    bulk_action_serializers: dict[str, type[serializers.Serializer]],
    bulk_action_response_serializers: dict[str, type[serializers.Serializer]],
    field_subresources: tuple[FieldSubresourceSpec, ...],
) -> None:
    """Decorate generated actions when drf-spectacular is installed.

    CRUDFactory does not require drf-spectacular at runtime.  When users install
    it, this optional decorator path provides separate request/response schemas
    for write actions and documents generated query parameters for list actions.
    """
    try:
        from drf_spectacular.utils import OpenApiParameter, extend_schema
    except ImportError:
        return

    list_parameters = list_parameters_for_schema(
        filter_specs=filter_specs,
        order_specs=order_specs,
        list_query=list_query,
        OpenApiParameter=OpenApiParameter,
    )
    viewset_class.list = extend_schema(
        parameters=list_parameters,
        responses=response_serializer(many=True),
    )(viewset_class.list)
    viewset_class.retrieve = extend_schema(
        responses=response_serializer,
    )(viewset_class.retrieve)
    if read_only:
        decorate_custom_actions(
            viewset_class=viewset_class,
            custom_actions=custom_actions,
            custom_action_serializers=custom_action_serializers,
            custom_action_response_serializers=custom_action_response_serializers,
            OpenApiParameter=OpenApiParameter,
            extend_schema=extend_schema,
        )
        decorate_grouped_actions(
            viewset_class=viewset_class,
            grouped_actions=grouped_actions,
            grouped_action_response_serializers=grouped_action_response_serializers,
            OpenApiParameter=OpenApiParameter,
            extend_schema=extend_schema,
        )
        decorate_bulk_actions(
            viewset_class=viewset_class,
            bulk_actions=bulk_actions,
            bulk_action_serializers=bulk_action_serializers,
            bulk_action_response_serializers=bulk_action_response_serializers,
            extend_schema=extend_schema,
        )
        decorate_field_subresources(
            viewset_class=viewset_class,
            model=model,
            field_subresources=field_subresources,
            extend_schema=extend_schema,
        )
        return

    viewset_class.create = extend_schema(
        request=create_serializer,
        responses={201: response_serializer},
    )(viewset_class.create)
    viewset_class.update = extend_schema(
        request=update_serializer,
        responses=response_serializer,
    )(viewset_class.update)
    viewset_class.partial_update = extend_schema(
        request=patch_serializer,
        responses=response_serializer,
    )(viewset_class.partial_update)
    decorate_custom_actions(
        viewset_class=viewset_class,
        custom_actions=custom_actions,
        custom_action_serializers=custom_action_serializers,
        custom_action_response_serializers=custom_action_response_serializers,
        OpenApiParameter=OpenApiParameter,
        extend_schema=extend_schema,
    )
    decorate_grouped_actions(
        viewset_class=viewset_class,
        grouped_actions=grouped_actions,
        grouped_action_response_serializers=grouped_action_response_serializers,
        OpenApiParameter=OpenApiParameter,
        extend_schema=extend_schema,
    )
    decorate_bulk_actions(
        viewset_class=viewset_class,
        bulk_actions=bulk_actions,
        bulk_action_serializers=bulk_action_serializers,
        bulk_action_response_serializers=bulk_action_response_serializers,
        extend_schema=extend_schema,
    )
    decorate_field_subresources(
        viewset_class=viewset_class,
        model=model,
        field_subresources=field_subresources,
        extend_schema=extend_schema,
    )


def decorate_custom_actions(
    *,
    viewset_class: type[ModelViewSet],
    custom_actions: tuple[CustomActionSpec[Any], ...],
    custom_action_serializers: dict[str, type[serializers.Serializer]],
    custom_action_response_serializers: dict[str, type[serializers.Serializer]],
    OpenApiParameter: type[Any],
    extend_schema: Any,
) -> None:
    """Decorate typed custom actions with request/response schemas."""
    custom_actions_by_name = {
        custom_action.name: custom_action for custom_action in custom_actions
    }
    for action_name, request_serializer in custom_action_serializers.items():
        custom_action = custom_actions_by_name[action_name]
        response_serializer = custom_action_response_serializers[action_name]
        action_method = getattr(viewset_class, action_name)
        if custom_action.request_source == "query":
            query_dataclass = custom_action.query_dataclass
            if query_dataclass is None:
                msg = f"Custom action {custom_action.name!r} is missing query_dataclass."
                raise TypeError(msg)
            decorated_method = extend_schema(
                request=None,
                parameters=dataclass_query_parameters_for_schema(
                    query_dataclass,
                    OpenApiParameter=OpenApiParameter,
                ),
                responses=response_serializer,
            )(action_method)
            setattr(viewset_class, action_name, decorated_method)
            continue
        setattr(
            viewset_class,
            action_name,
            extend_schema(
                request=request_serializer,
                responses=response_serializer,
            )(action_method),
        )


def decorate_grouped_actions(
    *,
    viewset_class: type[ModelViewSet],
    grouped_actions: tuple[Any, ...],
    grouped_action_response_serializers: dict[str, type[serializers.Serializer]],
    OpenApiParameter: type[Any],
    extend_schema: Any,
) -> None:
    """Decorate grouped collection actions with query-param schemas."""
    for grouped_action in grouped_actions:
        response_serializer = grouped_action_response_serializers[grouped_action.name]
        action_method = getattr(viewset_class, grouped_action.name)
        setattr(
            viewset_class,
            grouped_action.name,
            extend_schema(
                request=None,
                parameters=grouped_action_parameters_for_schema(
                    grouped_action=grouped_action,
                    OpenApiParameter=OpenApiParameter,
                ),
                responses=response_serializer,
            )(action_method),
        )


def decorate_bulk_actions(
    *,
    viewset_class: type[ModelViewSet],
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    bulk_action_serializers: dict[str, type[serializers.Serializer]],
    bulk_action_response_serializers: dict[str, type[serializers.Serializer]],
    extend_schema: Any,
) -> None:
    """Decorate generated bulk mutation endpoints with list-body schemas."""
    for bulk_action in bulk_actions:
        request_serializer = bulk_action_serializers[bulk_action.name]
        response_serializer = bulk_action_response_serializers[bulk_action.name]
        action_method = getattr(viewset_class, bulk_action.name)
        setattr(
            viewset_class,
            bulk_action.name,
            extend_schema(
                request=request_serializer(many=True),
                responses=response_serializer,
                description=bulk_action_description(bulk_action),
            )(action_method),
        )


def decorate_field_subresources(
    *,
    viewset_class: type[ModelViewSet],
    model: type[models.Model],
    field_subresources: tuple[FieldSubresourceSpec, ...],
    extend_schema: Any,
) -> None:
    """Decorate generated field endpoints with raw payload request/response schemas."""
    for field_subresource in field_subresources:
        action_method = getattr(viewset_class, field_subresource.field_name)
        request_type = openapi_field_payload_type(model=model, field_name=field_subresource.field_name)
        responses: dict[int, Any] = {200: request_type}
        request_schema: Any = request_type if "patch" in field_subresource.methods else None
        setattr(
            viewset_class,
            field_subresource.field_name,
            extend_schema(
                request=request_schema,
                responses=responses,
                description=field_subresource_description(field_subresource),
            )(action_method),
        )


def list_parameters_for_schema(
    *,
    filter_specs: tuple[FilterSpec, ...],
    order_specs: tuple[OrderSpec, ...],
    list_query: type[object] | None = None,
    OpenApiParameter: type[Any],
) -> list[Any]:
    """Return OpenAPI query parameters for generated list filters/orderings."""
    parameters = [
        OpenApiParameter(
            name=filter_spec.query_param,
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description=f"Filter by `{filter_spec.lookup}`.",
        )
        for filter_spec in filter_specs
    ]
    if order_specs:
        allowed_ordering = ", ".join(order_spec.query_name for order_spec in order_specs)
        parameters.append(
            OpenApiParameter(
                name=ORDERING_QUERY_PARAM,
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Comma-separated ordering fields. Prefix with '-' for "
                    f"descending order. Allowed fields: {allowed_ordering}."
                ),
            )
        )
    if list_query is None:
        return parameters
    seen_names = {parameter.name for parameter in parameters}
    for parameter in dataclass_query_parameters_for_schema(
        list_query,
        OpenApiParameter=OpenApiParameter,
        label="List query field",
    ):
        if parameter.name in seen_names:
            continue
        seen_names.add(parameter.name)
        parameters.append(parameter)
    return parameters


def grouped_action_parameters_for_schema(
    *,
    grouped_action: Any,
    OpenApiParameter: type[Any],
) -> list[Any]:
    """Return OpenAPI query parameters for one grouped collection action."""
    parameters: list[Any] = []
    seen_names: set[str] = set()
    for parameter in dataclass_query_parameters_for_schema(
        grouped_action.query_dataclass,
        OpenApiParameter=OpenApiParameter,
    ):
        seen_names.add(parameter.name)
        parameters.append(parameter)
    for parameter in list_parameters_for_schema(
        filter_specs=source_filter_specs_from_dataclass(grouped_action.query_dataclass),
        order_specs=source_order_specs_from_dataclass(grouped_action.query_dataclass),
        OpenApiParameter=OpenApiParameter,
    ):
        if parameter.name in seen_names:
            continue
        seen_names.add(parameter.name)
        parameters.append(parameter)
    return parameters


def dataclass_query_parameters_for_schema(
    dataclass_type: type[Any],
    *,
    OpenApiParameter: type[Any],
    label: str = "Grouped action query field",
) -> list[Any]:
    """Return OpenAPI query parameters for exact-name grouped query DTO fields."""
    ensure_dataclass_type("grouped action query dataclass", dataclass_type)
    serializer_fields = build_serializer_fields(dataclass_type)
    type_hints = get_type_hints(dataclass_type)
    parameters: list[Any] = []
    for dataclass_field in fields(dataclass_type):
        serializer_field = serializer_fields[dataclass_field.name]
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        parameters.append(
            OpenApiParameter(
                name=dataclass_field.name,
                type=openapi_query_type(field_type),
                location=OpenApiParameter.QUERY,
                required=is_required_dataclass_field(dataclass_field),
                description=(
                    f"{label} `{dataclass_field.name}`."
                    if not serializer_field.help_text
                    else str(serializer_field.help_text)
                ),
            )
        )
    return parameters


def openapi_query_type(field_type: Any) -> Any:
    """Return a simple OpenAPI query parameter type for one supported field type."""
    inner_type = unwrap_optional_type(field_type)[0]
    origin = get_origin(inner_type)
    if origin is list:
        return str
    if inner_type in (str, int, float, bool, dt.date, dt.datetime, Decimal, UUID):
        return inner_type
    return str


def openapi_field_payload_type(
    *,
    model: type[models.Model],
    field_name: str,
) -> Any:
    """Return a simple OpenAPI payload type for one direct model field."""
    try:
        from drf_spectacular.types import OpenApiTypes
    except ImportError:
        OpenApiTypes = None

    django_field = direct_model_field(model, field_name)
    if isinstance(django_field, models.JSONField):
        return OpenApiTypes.OBJECT if OpenApiTypes is not None else dict[str, Any]
    if isinstance(django_field, (models.CharField, models.TextField)):
        return str
    if isinstance(django_field, models.BooleanField):
        return bool
    if isinstance(django_field, models.IntegerField):
        return int
    if isinstance(django_field, (models.DecimalField, models.FloatField)):
        return float
    return str


def field_subresource_description(field_subresource: FieldSubresourceSpec) -> str:
    """Return a small schema description for one field endpoint."""
    if "patch" in field_subresource.methods:
        return (
            f"Read or patch the `{field_subresource.field_name}` field directly. "
            f"PATCH uses `{field_subresource.patch_mode}` semantics."
        )
    return f"Read the `{field_subresource.field_name}` field directly."


def bulk_action_description(bulk_action: BulkActionSpec[Any]) -> str:
    """Return a short OpenAPI description for one generated bulk endpoint."""
    return (
        f"Bulk `{bulk_action.kind}` endpoint over a JSON list payload. "
        f"Transaction mode: `{bulk_action.transaction_mode}`."
    )


def is_required_dataclass_field(dataclass_field: Field[Any]) -> bool:
    """Return True when a grouped query field has no default value."""
    return dataclass_field.default is MISSING and dataclass_field.default_factory is MISSING
