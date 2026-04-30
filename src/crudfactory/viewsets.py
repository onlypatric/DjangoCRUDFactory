from __future__ import annotations

from typing import Any, Callable, Sequence, cast

from django.db import models
from rest_framework import serializers, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.pagination import BasePagination
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from ._acl_runtime import (
    enforce_create_acl,
    enforce_custom_action_acl,
    enforce_instance_acl,
    enforce_target_patch_acl,
    enforce_target_update_acl,
    filter_collection_for_acl,
    filter_grouped_collection_for_acl,
)
from .acl import ACLActionConfig, ACLConfig
from .actions import CustomActionSpec, GroupedCollectionActionSpec
from .dataclass_serializers import build_serializer_from_dataclass
from .filters import FilterSpec, apply_filter_specs, response_dataclass_from_mapper
from .inputs import serializer_to_dataclass
from .ordering import OrderSpec, apply_order_specs
from .response import dataclass_instance_to_response_data, map_instance_to_response_data
from .schema import (
    apply_schema_metadata,
    build_response_serializer_from_dataclass,
)
from .stats import (
    AggregateStatSpec,
    annotate_queryset_with_stat_specs,
    instance_with_stat_annotations,
)
from .source_queries import (
    query_param_names_from_dataclass,
    source_filter_specs_from_dataclass,
    source_order_specs_from_dataclass,
)
from .types import (
    CreateDTO,
    CreateHandler,
    M,
    PartialUpdateHandler,
    PatchDTO,
    ResponseDTO,
    ResponseMapper,
    UpdateDTO,
    UpdateHandler,
)

__all__: list[str] = []


def build_crud_viewset_class(
    *,
    model: type[M],
    response_mapper: ResponseMapper[M, ResponseDTO],
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    custom_actions: tuple[CustomActionSpec[M], ...],
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    read_only: bool,
    queryset: models.QuerySet[M] | None,
    lookup_field: str,
    lookup_url_kwarg: str | None,
    permission_classes: tuple[type[BasePermission], ...] | None,
    authentication_classes: tuple[type[BaseAuthentication], ...] | None,
    pagination_class: type[BasePagination] | None,
    filter_specs: tuple[FilterSpec, ...],
    order_specs: tuple[OrderSpec, ...],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> type[ModelViewSet]:
    """Build the DRF ModelViewSet subclass used by CRUDFactory.

    DRF routers expect a class, not an instance.  This function closes over the
    user's model, DTOs, and hooks, then returns a small generated subclass that
    implements the five CRUD actions with the configured contracts.
    """
    serializers_by_action = build_action_serializers_for_mode(
        model=model,
        create_input=create_input,
        update_input=update_input,
        partial_update_input=partial_update_input,
        read_only=read_only,
    )
    response_serializer = build_response_serializer_for_mapper(
        model=model,
        response_mapper=response_mapper,
    )
    custom_action_serializers = build_custom_action_serializers(custom_actions)
    custom_action_response_serializers = build_custom_action_response_serializers(
        custom_actions
    )
    grouped_action_serializers = build_grouped_action_serializers(grouped_actions)
    grouped_action_response_serializers = build_grouped_action_response_serializers(
        grouped_actions
    )
    viewset_class = create_viewset_class(
        model=model,
        response_mapper=response_mapper,
        create_input=create_input,
        update_input=update_input,
        partial_update_input=partial_update_input,
        create_handler=create_handler,
        update_handler=update_handler,
        partial_update_handler=partial_update_handler,
        custom_actions=custom_actions,
        grouped_actions=grouped_actions,
        acl=acl,
        read_only=read_only,
        serializers_by_action=serializers_by_action,
        custom_action_serializers=custom_action_serializers,
        custom_action_response_serializers=custom_action_response_serializers,
        grouped_action_serializers=grouped_action_serializers,
        response_serializer=response_serializer,
        queryset=queryset,
        lookup_field=lookup_field,
        lookup_url_kwarg=lookup_url_kwarg,
        filter_specs=filter_specs,
        order_specs=order_specs,
        stat_specs=stat_specs,
    )
    apply_schema_metadata(
        viewset_class,
        model=model,
        response_serializer=response_serializer,
        create_serializer=serializers_by_action.get("create", serializers.Serializer),
        update_serializer=serializers_by_action.get("update", serializers.Serializer),
        patch_serializer=serializers_by_action.get("partial_update", serializers.Serializer),
        read_only=read_only,
        filter_specs=filter_specs,
        order_specs=order_specs,
        custom_action_serializers=custom_action_serializers,
        custom_action_response_serializers=custom_action_response_serializers,
        grouped_actions=grouped_actions,
        grouped_action_serializers=grouped_action_serializers,
        grouped_action_response_serializers=grouped_action_response_serializers,
    )
    apply_optional_viewset_attributes(
        viewset_class,
        permission_classes=permission_classes,
        authentication_classes=authentication_classes,
        pagination_class=pagination_class,
    )
    return viewset_class


def build_response_serializer_for_mapper(
    *,
    model: type[M],
    response_mapper: ResponseMapper[M, ResponseDTO],
) -> type[serializers.Serializer]:
    """Build the schema serializer for successful response DTOs."""
    response_dataclass = response_dataclass_from_mapper(response_mapper)
    if response_dataclass is None:
        return serializers.Serializer
    return build_response_serializer_from_dataclass(
        response_dataclass,
        name=f"{response_dataclass.__name__}Serializer",
    )


def build_action_serializers(
    *,
    model: type[M],
    create_input: type[CreateDTO],
    update_input: type[UpdateDTO],
    partial_update_input: type[PatchDTO],
) -> dict[str, type[serializers.Serializer]]:
    """Generate one request serializer per write action."""
    return {
        "create": build_serializer_from_dataclass(
            create_input,
            name=f"{create_input.__name__}Serializer",
        ),
        "update": build_serializer_from_dataclass(
            update_input,
            name=f"{update_input.__name__}Serializer",
        ),
        "partial_update": build_serializer_from_dataclass(
            partial_update_input,
            name=f"{partial_update_input.__name__}Serializer",
        ),
    }


def build_custom_action_serializers(
    custom_actions: tuple[CustomActionSpec[M], ...],
) -> dict[str, type[serializers.Serializer]]:
    """Generate one request serializer per typed custom action."""
    return {
        custom_action.name: build_serializer_from_dataclass(
            custom_action.input_dataclass,
            name=f"{custom_action.input_dataclass.__name__}Serializer",
        )
        for custom_action in custom_actions
    }


def build_custom_action_response_serializers(
    custom_actions: tuple[CustomActionSpec[M], ...],
) -> dict[str, type[serializers.Serializer]]:
    """Generate one response serializer per typed custom action."""
    return {
        custom_action.name: build_response_serializer_from_dataclass(
            custom_action.response_dataclass,
            name=f"{custom_action.response_dataclass.__name__}Serializer",
        )
        for custom_action in custom_actions
    }


def build_grouped_action_serializers(
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
) -> dict[str, type[serializers.Serializer]]:
    """Generate one query serializer per grouped collection action."""
    return {
        grouped_action.name: build_serializer_from_dataclass(
            grouped_action.query_dataclass,
            name=f"{grouped_action.query_dataclass.__name__}Serializer",
        )
        for grouped_action in grouped_actions
    }


def build_grouped_action_response_serializers(
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
) -> dict[str, type[serializers.Serializer]]:
    """Generate one response serializer per grouped collection action."""
    return {
        grouped_action.name: build_response_serializer_from_dataclass(
            grouped_action.response_dataclass,
            name=f"{grouped_action.response_dataclass.__name__}Serializer",
        )
        for grouped_action in grouped_actions
    }


def build_action_serializers_for_mode(
    *,
    model: type[M],
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    read_only: bool,
) -> dict[str, type[serializers.Serializer]]:
    """Return write serializers, or a tiny placeholder for read-only factories."""
    if read_only:
        return {"default": serializers.Serializer}
    if create_input is None or update_input is None or partial_update_input is None:
        msg = "Write input dataclasses are required unless read_only=True."
        raise TypeError(msg)
    return build_action_serializers(
        model=model,
        create_input=create_input,
        update_input=update_input,
        partial_update_input=partial_update_input,
    )


def create_viewset_class(
    *,
    model: type[M],
    response_mapper: ResponseMapper[M, ResponseDTO],
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    custom_actions: tuple[CustomActionSpec[M], ...],
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    read_only: bool,
    serializers_by_action: dict[str, type[serializers.Serializer]],
    custom_action_serializers: dict[str, type[serializers.Serializer]],
    custom_action_response_serializers: dict[str, type[serializers.Serializer]],
    grouped_action_serializers: dict[str, type[serializers.Serializer]],
    response_serializer: type[serializers.Serializer],
    queryset: models.QuerySet[M] | None,
    lookup_field: str,
    lookup_url_kwarg: str | None,
    filter_specs: tuple[FilterSpec, ...],
    order_specs: tuple[OrderSpec, ...],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> type[ModelViewSet]:
    """Create the actual subclass with readable action methods."""
    default_serializer = serializers_by_action.get("default", response_serializer)
    create_serializer = serializers_by_action.get("create", default_serializer)
    update_serializer = serializers_by_action.get("update", default_serializer)
    patch_serializer = serializers_by_action.get("partial_update", default_serializer)
    viewset_queryset = annotate_queryset_with_stat_specs(
        queryset_for_viewset(model, queryset),
        stat_specs,
    )
    viewset_lookup_field = lookup_field
    viewset_lookup_url_kwarg = lookup_url_kwarg

    class GeneratedCRUDViewSet(ModelViewSet):
        queryset = viewset_queryset
        lookup_field = viewset_lookup_field
        lookup_url_kwarg = viewset_lookup_url_kwarg
        serializer_class = create_serializer
        http_method_names = http_method_names_for_mode(read_only)

        def get_serializer_class(self) -> type[serializers.Serializer]:
            return serializer_for_action(
                action=self.action,
                default_serializer=create_serializer,
                response_serializer=response_serializer,
                update_serializer=update_serializer,
                patch_serializer=patch_serializer,
                custom_action_serializers=custom_action_serializers,
            )

        def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
            queryset = self.filter_queryset(self.get_queryset())
            queryset = apply_filter_specs(queryset, request.query_params, filter_specs)
            queryset = apply_order_specs(queryset, request.query_params, order_specs)
            filtered_collection = filter_collection_for_acl(
                queryset=queryset,
                request=request,
                acl=acl,
                action_config=acl_action(acl, "list_action"),
            )
            return list_response(
                viewset=self,
                queryset=filtered_collection,
                response_mapper=response_mapper,
                stat_specs=stat_specs,
            )

        def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
            instance = self.get_object()
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "retrieve_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            return retrieve_response(instance, response_mapper, stat_specs)

        def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
            ensure_writes_are_allowed(read_only, "POST")
            create_dataclass = require_write_input(create_input, "create")
            create_fn = require_write_handler(create_handler, "create")
            dto = validated_input_dataclass(
                serializer_class=create_serializer,
                request=request,
                dataclass_type=create_dataclass,
            )
            enforce_create_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "create_action"),
                dto=dto,
            )
            instance = create_fn(dto)
            return create_response(
                viewset=self,
                instance=instance,
                response_mapper=response_mapper,
                stat_specs=stat_specs,
            )

        def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
            ensure_writes_are_allowed(read_only, "PUT")
            update_dataclass = require_write_input(update_input, "update")
            update_fn = require_write_handler(update_handler, "update")
            instance = self.get_object()
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "update_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            dto = validated_input_dataclass(
                serializer_class=update_serializer,
                request=request,
                dataclass_type=update_dataclass,
            )
            enforce_target_update_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "update_action"),
                instance=instance,
                dto=dto,
                resolver=resource_ref_from_update_input(acl),
            )
            updated_instance = update_fn(instance, dto)
            return update_response(
                viewset=self,
                instance=updated_instance,
                response_mapper=response_mapper,
                stat_specs=stat_specs,
            )

        def partial_update(
            self,
            request: Request,
            *args: Any,
            **kwargs: Any,
        ) -> Response:
            ensure_writes_are_allowed(read_only, "PATCH")
            patch_dataclass = require_write_input(
                partial_update_input,
                "partial_update",
            )
            patch_fn = require_write_handler(
                partial_update_handler,
                "partial_update",
            )
            instance = self.get_object()
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "partial_update_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            dto = validated_input_dataclass(
                serializer_class=patch_serializer,
                request=request,
                dataclass_type=patch_dataclass,
                partial=True,
                fill_missing_optional=True,
            )
            enforce_target_patch_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "partial_update_action"),
                instance=instance,
                dto=dto,
                resolver=resource_ref_from_patch_input(acl),
            )
            updated_instance = patch_fn(instance, dto)
            return update_response(
                viewset=self,
                instance=updated_instance,
                response_mapper=response_mapper,
                stat_specs=stat_specs,
            )

        def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
            ensure_writes_are_allowed(read_only, "DELETE")
            instance = self.get_object()
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "destroy_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

    attach_custom_actions(
        viewset_class=GeneratedCRUDViewSet,
        custom_actions=custom_actions,
        custom_action_serializers=custom_action_serializers,
        acl=acl,
    )
    attach_grouped_collection_actions(
        viewset_class=GeneratedCRUDViewSet,
        grouped_actions=grouped_actions,
        grouped_action_serializers=grouped_action_serializers,
        acl=acl,
    )
    name_generated_viewset(GeneratedCRUDViewSet, model)
    return GeneratedCRUDViewSet


def attach_custom_actions(
    *,
    viewset_class: type[ModelViewSet],
    custom_actions: tuple[CustomActionSpec[M], ...],
    custom_action_serializers: dict[str, type[serializers.Serializer]],
    acl: ACLConfig[M, Any, Any, Any] | None,
) -> None:
    """Attach DRF extra action methods to the generated ViewSet class."""
    for custom_action in custom_actions:
        action_method = build_custom_action_method(
            custom_action=custom_action,
            serializer_class=custom_action_serializers[custom_action.name],
            acl=acl,
        )
        setattr(viewset_class, custom_action.name, action_method)


def attach_grouped_collection_actions(
    *,
    viewset_class: type[ModelViewSet],
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
    grouped_action_serializers: dict[str, type[serializers.Serializer]],
    acl: ACLConfig[M, Any, Any, Any] | None,
) -> None:
    """Attach grouped read-only collection action methods to the ViewSet class."""
    for grouped_action in grouped_actions:
        action_method = build_grouped_collection_action_method(
            grouped_action=grouped_action,
            serializer_class=grouped_action_serializers[grouped_action.name],
            acl=acl,
        )
        setattr(viewset_class, grouped_action.name, action_method)


def build_custom_action_method(
    *,
    custom_action: CustomActionSpec[M],
    serializer_class: type[serializers.Serializer],
    acl: ACLConfig[M, Any, Any, Any] | None,
) -> Callable[..., Response]:
    """Build one typed DRF extra action method."""

    def custom_action_method(
        self: ModelViewSet,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        dto = validated_input_dataclass(
            serializer_class=serializer_class,
            request=request,
            dataclass_type=custom_action.input_dataclass,
        )
        if custom_action.detail:
            instance = self.get_object()
            enforce_custom_action_acl(
                request=request,
                acl=acl,
                custom_action=custom_action,
                instance=instance,
                dto=dto,
            )
            response_dto = custom_action.handler(instance, dto)
        else:
            queryset = self.filter_queryset(self.get_queryset())
            enforce_custom_action_acl(
                request=request,
                acl=acl,
                custom_action=custom_action,
                instance=None,
                dto=dto,
            )
            response_dto = custom_action.handler(queryset, dto)
        return Response(dataclass_instance_to_response_data(response_dto))

    custom_action_method.__name__ = custom_action.name
    custom_action_method.__qualname__ = custom_action.name
    custom_action_method.__doc__ = (
        f"Generated typed custom action `{custom_action.name}`."
    )
    return action(
        detail=custom_action.detail,
        methods=cast(Any, list(custom_action.methods)),
        url_path=custom_action.url_path,
        url_name=custom_action.url_name,
    )(custom_action_method)


def build_grouped_collection_action_method(
    *,
    grouped_action: GroupedCollectionActionSpec[M],
    serializer_class: type[serializers.Serializer],
    acl: ACLConfig[M, Any, Any, Any] | None,
) -> Callable[..., Response]:
    """Build one grouped read-only collection action method."""
    source_filter_specs = source_filter_specs_from_dataclass(grouped_action.query_dataclass)
    source_order_specs = source_order_specs_from_dataclass(grouped_action.query_dataclass)

    def grouped_collection_action_method(
        self: ModelViewSet,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        queryset = apply_filter_specs(queryset, request.query_params, source_filter_specs)
        queryset = apply_order_specs(queryset, request.query_params, source_order_specs)
        filtered_collection = filter_grouped_collection_for_acl(
            queryset=queryset,
            request=request,
            acl=acl,
            source_acl=grouped_action.source_acl,
        )
        dto = validated_query_dataclass(
            serializer_class=serializer_class,
            request=request,
            dataclass_type=grouped_action.query_dataclass,
        )
        response_dto = grouped_action.handler(filtered_collection, dto)
        return Response(dataclass_instance_to_response_data(response_dto))

    grouped_collection_action_method.__name__ = grouped_action.name
    grouped_collection_action_method.__qualname__ = grouped_action.name
    grouped_collection_action_method.__doc__ = (
        f"Generated grouped collection action `{grouped_action.name}`."
    )
    return action(
        detail=False,
        methods=cast(Any, list(grouped_action.methods)),
        url_path=grouped_action.url_path,
        url_name=grouped_action.url_name,
    )(grouped_collection_action_method)


def http_method_names_for_mode(read_only: bool) -> list[str]:
    """Return allowed HTTP methods for the generated ViewSet mode."""
    if read_only:
        return ["get", "head", "options"]
    return ["get", "post", "put", "patch", "delete", "head", "options"]


def ensure_writes_are_allowed(read_only: bool, method: str) -> None:
    """Raise DRF's normal 405 error when a read-only factory receives a write."""
    if read_only:
        raise MethodNotAllowed(method)


def require_write_input(
    input_dataclass: type[Any] | None,
    action: str,
) -> type[Any]:
    """Return a write input dataclass or fail clearly for bad configuration."""
    if input_dataclass is None:
        msg = f"{action} requires a write DTO unless read_only=True."
        raise TypeError(msg)
    return input_dataclass


def require_write_handler(
    handler: Callable[..., M] | None,
    action: str,
) -> Callable[..., M]:
    """Return a write handler or fail clearly for bad configuration."""
    if handler is None:
        msg = f"{action} requires a write handler unless read_only=True."
        raise TypeError(msg)
    return handler


def queryset_for_viewset(
    model: type[M],
    queryset: models.QuerySet[M] | None,
) -> models.QuerySet[M]:
    """Return the configured queryset or the model's default manager queryset."""
    if queryset is not None:
        return queryset
    return model.objects.all()


def serializer_for_action(
    *,
    action: str,
    default_serializer: type[serializers.Serializer],
    response_serializer: type[serializers.Serializer],
    update_serializer: type[serializers.Serializer],
    patch_serializer: type[serializers.Serializer],
    custom_action_serializers: dict[str, type[serializers.Serializer]],
) -> type[serializers.Serializer]:
    """Return the request serializer that matches the current ViewSet action."""
    custom_action_serializer = custom_action_serializers.get(action)
    if custom_action_serializer is not None:
        return custom_action_serializer
    if action in ("list", "retrieve"):
        return response_serializer
    if action == "update":
        return update_serializer
    if action == "partial_update":
        return patch_serializer
    return default_serializer


def acl_action(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    action_name: str,
) -> ACLActionConfig | None:
    """Return one ACL action config from the factory-level ACL block."""
    if acl is None:
        return None
    return getattr(acl, action_name)


def resource_ref_from_instance(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
) -> Callable[[M], object] | None:
    """Return the instance-level resource resolver from ACL config."""
    if acl is None:
        return None
    return acl.resource_ref_from_instance


def resource_ref_from_update_input(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
) -> Callable[[M, UpdateDTO], object] | None:
    """Return the update target resolver from ACL config."""
    if acl is None:
        return None
    return acl.resource_ref_from_update_input


def resource_ref_from_patch_input(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
) -> Callable[[M, PatchDTO], object] | None:
    """Return the patch target resolver from ACL config."""
    if acl is None:
        return None
    return acl.resource_ref_from_patch_input


def list_response(
    *,
    viewset: ModelViewSet,
    queryset: models.QuerySet[M] | Sequence[M],
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> Response:
    """Return a DTO-shaped response for a list action, with pagination support."""
    page = viewset.paginate_queryset(cast(Any, queryset))
    if page is not None:
        data = response_data_for_many(page, response_mapper, stat_specs)
        return viewset.get_paginated_response(data)

    data = response_data_for_many(queryset, response_mapper, stat_specs)
    return Response(data)


def retrieve_response(
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> Response:
    """Return a DTO-shaped response for one object."""
    return Response(response_data_for_one(instance, response_mapper, stat_specs))


def create_response(
    *,
    viewset: ModelViewSet,
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> Response:
    """Return a DTO-shaped 201 response after a create hook succeeds."""
    response_instance = response_instance_with_stats(
        viewset=viewset,
        instance=instance,
        stat_specs=stat_specs,
    )
    return Response(
        response_data_for_one(response_instance, response_mapper, stat_specs),
        status=status.HTTP_201_CREATED,
    )


def update_response(
    *,
    viewset: ModelViewSet,
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> Response:
    """Return a DTO-shaped 200 response after an update hook succeeds."""
    response_instance = response_instance_with_stats(
        viewset=viewset,
        instance=instance,
        stat_specs=stat_specs,
    )
    return Response(response_data_for_one(response_instance, response_mapper, stat_specs))


def response_data_for_many(
    instances: Any,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> list[dict[str, Any]]:
    """Map every model instance in an iterable/queryset into response data."""
    return [
        response_data_for_one(instance, response_mapper, stat_specs)
        for instance in instances
    ]


def response_data_for_one(
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
) -> dict[str, Any]:
    """Map one model instance into JSON-ready response data."""
    return map_instance_to_response_data(instance, response_mapper, stat_specs)


def response_instance_with_stats(
    *,
    viewset: ModelViewSet,
    instance: M,
    stat_specs: tuple[AggregateStatSpec, ...],
) -> M:
    """Reload write-hook results so create/update responses include fresh stats."""
    return instance_with_stat_annotations(
        instance=instance,
        queryset=viewset.get_queryset(),
        stat_specs=stat_specs,
    )


def validated_input_dataclass(
    *,
    serializer_class: type[serializers.Serializer],
    request: Request,
    dataclass_type: type[Any],
    partial: bool = False,
    fill_missing_optional: bool = False,
) -> Any:
    """Validate request.data and return the configured input dataclass."""
    serializer = serializer_class(data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    return serializer_to_dataclass(
        serializer,
        dataclass_type,
        fill_missing_optional=fill_missing_optional,
    )


def validated_query_dataclass(
    *,
    serializer_class: type[serializers.Serializer],
    request: Request,
    dataclass_type: type[Any],
) -> Any:
    """Validate request.query_params and return the configured grouped query dataclass."""
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer_to_dataclass(serializer, dataclass_type)


def apply_optional_viewset_attributes(
    viewset_class: type[ModelViewSet],
    *,
    permission_classes: tuple[type[BasePermission], ...] | None,
    authentication_classes: tuple[type[BaseAuthentication], ...] | None,
    pagination_class: type[BasePagination] | None,
) -> None:
    """Attach optional DRF class attributes only when the user configured them."""
    if permission_classes is not None:
        viewset_class.permission_classes = permission_classes
    if authentication_classes is not None:
        viewset_class.authentication_classes = authentication_classes
    if pagination_class is not None:
        viewset_class.pagination_class = pagination_class


def name_generated_viewset(
    viewset_class: type[ModelViewSet],
    model: type[models.Model],
) -> None:
    """Give the dynamic class a useful name for debugging and DRF schemas."""
    viewset_class.__name__ = f"{model.__name__}CRUDViewSet"
    viewset_class.__qualname__ = viewset_class.__name__
