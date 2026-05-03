from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any, Callable, Sequence, cast

from django.db import models
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
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
from .annotations import (
    AnnotationSpec,
    annotate_queryset_with_annotation_specs,
    instance_with_annotation_specs,
)
from .bulk_actions import (
    BulkActionSpec,
    BulkFieldErrorDTO,
    BulkMutationResultDTO,
    BulkRowErrorDTO,
)
from .dataclass_serializers import build_serializer_from_dataclass
from .filters import FilterSpec, apply_filter_specs, response_dataclass_from_mapper
from .field_subresources import (
    FieldSubresourceSpec,
    apply_field_subresource_patch,
    field_subresource_payload_label,
    read_field_payload,
    validated_field_payload,
)
from .list_queries import (
    ListQueryFilterSpec,
    ListQueryOrderingSpec,
    ListQuerySearchSpec,
    apply_list_query_dataclass,
)
from .lifecycle import (
    LifecycleConfig,
    apply_delete_lifecycle,
    apply_restore_lifecycle,
    lifecycle_filter_queryset,
    lifecycle_include_archived_requested,
)
from ._simple_writes import MODEL_FIELD_METADATA_KEY
from .inputs import override_dataclass, project_dataclass, serializer_to_dataclass
from .ordering import OrderSpec, apply_order_specs
from .parent_scopes import ParentScopeSpec, dataclass_parent_binding_field_name
from .query_plans import QueryPlan, apply_query_plan
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
    list_query: type[object] | None,
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    custom_actions: tuple[CustomActionSpec[M], ...],
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    field_subresources: tuple[FieldSubresourceSpec, ...],
    lifecycle: LifecycleConfig | None,
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
    list_query_filter_specs: tuple[ListQueryFilterSpec, ...],
    list_query_search_specs: tuple[ListQuerySearchSpec, ...],
    list_query_ordering_specs: tuple[ListQueryOrderingSpec, ...],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
    parent_scope: ParentScopeSpec | None,
    query_plan: QueryPlan,
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
    list_query_serializer = build_list_query_serializer(list_query)
    bulk_action_serializers = build_bulk_action_serializers(
        bulk_actions=bulk_actions,
        create_input=create_input,
    )
    bulk_action_response_serializers = build_bulk_action_response_serializers(
        bulk_actions
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
        bulk_actions=bulk_actions,
        lifecycle=lifecycle,
        acl=acl,
        read_only=read_only,
        serializers_by_action=serializers_by_action,
        custom_action_serializers=custom_action_serializers,
        custom_action_response_serializers=custom_action_response_serializers,
        grouped_action_serializers=grouped_action_serializers,
        list_query_serializer=list_query_serializer,
        bulk_action_serializers=bulk_action_serializers,
        response_serializer=response_serializer,
        field_subresources=field_subresources,
        queryset=queryset,
        lookup_field=lookup_field,
        lookup_url_kwarg=lookup_url_kwarg,
        filter_specs=filter_specs,
        order_specs=order_specs,
        list_query=list_query,
        list_query_filter_specs=list_query_filter_specs,
        list_query_search_specs=list_query_search_specs,
        list_query_ordering_specs=list_query_ordering_specs,
        stat_specs=stat_specs,
        annotation_specs=annotation_specs,
        parent_scope=parent_scope,
        query_plan=query_plan,
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
        list_query=list_query,
        lifecycle=lifecycle,
        custom_actions=custom_actions,
        custom_action_serializers=custom_action_serializers,
        custom_action_response_serializers=custom_action_response_serializers,
        grouped_actions=grouped_actions,
        grouped_action_serializers=grouped_action_serializers,
        grouped_action_response_serializers=grouped_action_response_serializers,
        bulk_actions=bulk_actions,
        bulk_action_serializers=bulk_action_serializers,
        bulk_action_response_serializers=bulk_action_response_serializers,
        field_subresources=field_subresources,
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


def build_list_query_serializer(
    list_query: type[object] | None,
) -> type[serializers.Serializer] | None:
    """Build the serializer used to validate advanced list-query DTOs."""
    if list_query is None:
        return None
    return build_serializer_from_dataclass(
        list_query,
        name=f"{list_query.__name__}Serializer",
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
            require_custom_action_dataclass(custom_action),
            name=f"{require_custom_action_dataclass(custom_action).__name__}Serializer",
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


def build_bulk_action_serializers(
    *,
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    create_input: type[CreateDTO] | None,
) -> dict[str, type[serializers.Serializer]]:
    """Generate one row serializer per bulk mutation endpoint."""
    serializers_by_name: dict[str, type[serializers.Serializer]] = {}
    for bulk_action in bulk_actions:
        dataclass_type = require_bulk_input_dataclass(
            bulk_action=bulk_action,
            create_input=create_input,
        )
        serializers_by_name[bulk_action.name] = build_serializer_from_dataclass(
            dataclass_type,
            name=f"{dataclass_type.__name__}Serializer",
        )
    return serializers_by_name


def build_bulk_action_response_serializers(
    bulk_actions: tuple[BulkActionSpec[Any], ...],
) -> dict[str, type[serializers.Serializer]]:
    """Generate the shared structured result serializer for bulk endpoints."""
    return {
        bulk_action.name: build_response_serializer_from_dataclass(
            BulkMutationResultDTO,
            name="BulkMutationResultDTOSerializer",
        )
        for bulk_action in bulk_actions
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
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    field_subresources: tuple[FieldSubresourceSpec, ...],
    lifecycle: LifecycleConfig | None,
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    read_only: bool,
    serializers_by_action: dict[str, type[serializers.Serializer]],
    custom_action_serializers: dict[str, type[serializers.Serializer]],
    custom_action_response_serializers: dict[str, type[serializers.Serializer]],
    grouped_action_serializers: dict[str, type[serializers.Serializer]],
    list_query_serializer: type[serializers.Serializer] | None,
    bulk_action_serializers: dict[str, type[serializers.Serializer]],
    response_serializer: type[serializers.Serializer],
    queryset: models.QuerySet[M] | None,
    lookup_field: str,
    lookup_url_kwarg: str | None,
    filter_specs: tuple[FilterSpec, ...],
    order_specs: tuple[OrderSpec, ...],
    list_query: type[object] | None,
    list_query_filter_specs: tuple[ListQueryFilterSpec, ...],
    list_query_search_specs: tuple[ListQuerySearchSpec, ...],
    list_query_ordering_specs: tuple[ListQueryOrderingSpec, ...],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
    parent_scope: ParentScopeSpec | None,
    query_plan: QueryPlan,
) -> type[ModelViewSet]:
    """Create the actual subclass with readable action methods."""
    default_serializer = serializers_by_action.get("default", response_serializer)
    create_serializer = serializers_by_action.get("create", default_serializer)
    update_serializer = serializers_by_action.get("update", default_serializer)
    patch_serializer = serializers_by_action.get("partial_update", default_serializer)
    viewset_queryset = annotate_queryset_with_annotation_specs(
        annotate_queryset_with_stat_specs(
            apply_query_plan(
                queryset_for_viewset(model, queryset),
                query_plan,
            ),
            stat_specs,
        ),
        annotation_specs,
    )
    viewset_lookup_field = lookup_field
    viewset_lookup_url_kwarg = lookup_url_kwarg

    class GeneratedCRUDViewSet(ModelViewSet):
        queryset = viewset_queryset
        lookup_field = viewset_lookup_field
        lookup_url_kwarg = viewset_lookup_url_kwarg
        serializer_class = create_serializer
        http_method_names = http_method_names_for_mode(read_only)

        def get_parent_instance(self) -> models.Model | None:
            if parent_scope is None:
                return None
            cached_parent = getattr(self, "_crudfactory_parent_instance", None)
            if cached_parent is not None:
                return cast(models.Model, cached_parent)
            parent_lookup_value = self.kwargs[parent_scope.parent_lookup_url_kwarg]
            parent_instance = get_object_or_404(
                parent_scope.parent_model,
                **{parent_scope.parent_lookup_field: parent_lookup_value},
            )
            self._crudfactory_parent_instance = parent_instance
            return cast(models.Model, parent_instance)

        def get_queryset(self) -> models.QuerySet[M]:
            queryset = cast(models.QuerySet[M], super().get_queryset())
            if parent_scope is None:
                scoped_queryset = queryset
            else:
                parent_instance = self.get_parent_instance()
                if parent_instance is None:
                    scoped_queryset = queryset
                else:
                    scoped_queryset = cast(
                        models.QuerySet[M],
                        queryset.filter(**{parent_scope.child_fk_field: parent_instance}),
                    )
            if lifecycle is None:
                return scoped_queryset
            action_name = getattr(self, "action", "")
            include_archived = lifecycle_include_archived_requested(
                lifecycle,
                self.request.query_params.get(lifecycle.include_archived_param or "")
                if hasattr(self, "request")
                else None,
            )
            if action_name == "list":
                if include_archived:
                    return scoped_queryset
                return cast(models.QuerySet[M], lifecycle_filter_queryset(scoped_queryset, lifecycle))
            if action_name in {"retrieve", "update", "partial_update", "destroy"}:
                if lifecycle.hide_archived_detail:
                    return cast(models.QuerySet[M], lifecycle_filter_queryset(scoped_queryset, lifecycle))
            return scoped_queryset

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
            if list_query is not None:
                if list_query_serializer is None:
                    msg = "Advanced list query configuration is missing its serializer."
                    raise TypeError(msg)
                query_dto = validated_query_dataclass(
                    serializer_class=list_query_serializer,
                    request=request,
                    dataclass_type=list_query,
                )
                queryset = apply_list_query_dataclass(
                    queryset,
                    query_dto,
                    filter_specs=list_query_filter_specs,
                    search_specs=list_query_search_specs,
                    ordering_specs=list_query_ordering_specs,
                )
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
                annotation_specs=annotation_specs,
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
            return retrieve_response(
                instance,
                response_mapper,
                stat_specs,
                annotation_specs,
            )

        def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
            ensure_writes_are_allowed(read_only, "POST")
            create_dataclass = require_write_input(create_input, "create")
            create_fn = require_write_handler(create_handler, "create")
            dto = validated_input_dataclass(
                serializer_class=create_serializer,
                request=request,
                dataclass_type=create_dataclass,
            )
            dto = bind_parent_scope_to_dto(
                dto=dto,
                parent_scope=parent_scope,
                parent_instance=self.get_parent_instance(),
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
                annotation_specs=annotation_specs,
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
            dto = bind_parent_scope_to_dto(
                dto=dto,
                parent_scope=parent_scope,
                parent_instance=self.get_parent_instance(),
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
                annotation_specs=annotation_specs,
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
            dto = bind_parent_scope_to_dto(
                dto=dto,
                parent_scope=parent_scope,
                parent_instance=self.get_parent_instance(),
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
                annotation_specs=annotation_specs,
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
            if lifecycle is None:
                self.perform_destroy(instance)
            else:
                apply_delete_lifecycle(cast(models.Model, instance), lifecycle)
            return Response(status=status.HTTP_204_NO_CONTENT)

    attach_custom_actions(
        viewset_class=GeneratedCRUDViewSet,
        custom_actions=custom_actions,
        custom_action_serializers=custom_action_serializers,
        acl=acl,
    )
    attach_lifecycle_actions(
        viewset_class=GeneratedCRUDViewSet,
        model=model,
        queryset=viewset_queryset,
        lifecycle=lifecycle,
        lookup_field=lookup_field,
        lookup_url_kwarg=lookup_url_kwarg,
        response_mapper=response_mapper,
        stat_specs=stat_specs,
        annotation_specs=annotation_specs,
        acl=acl,
        parent_scope=parent_scope,
    )
    attach_grouped_collection_actions(
        viewset_class=GeneratedCRUDViewSet,
        grouped_actions=grouped_actions,
        grouped_action_serializers=grouped_action_serializers,
        acl=acl,
    )
    attach_bulk_actions(
        viewset_class=GeneratedCRUDViewSet,
        create_input=create_input,
        update_input=update_input,
        partial_update_input=partial_update_input,
        create_handler=create_handler,
        update_handler=update_handler,
        partial_update_handler=partial_update_handler,
        bulk_actions=bulk_actions,
        bulk_action_serializers=bulk_action_serializers,
        lifecycle=lifecycle,
        acl=acl,
    )
    attach_field_subresources(
        viewset_class=GeneratedCRUDViewSet,
        model=model,
        field_subresources=field_subresources,
        acl=acl,
        read_only=read_only,
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


def attach_lifecycle_actions(
    *,
    viewset_class: type[ModelViewSet],
    model: type[M],
    queryset: models.QuerySet[M],
    lifecycle: LifecycleConfig | None,
    lookup_field: str,
    lookup_url_kwarg: str | None,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
    acl: ACLConfig[M, Any, Any, Any] | None,
    parent_scope: ParentScopeSpec | None,
) -> None:
    """Attach generated lifecycle actions such as restore."""
    if lifecycle is None or not lifecycle.restore_action:
        return
    action_method = build_restore_action_method(
        model=model,
        queryset=queryset,
        lifecycle=lifecycle,
        lookup_field=lookup_field,
        lookup_url_kwarg=lookup_url_kwarg,
        response_mapper=response_mapper,
        stat_specs=stat_specs,
        annotation_specs=annotation_specs,
        acl=acl,
        parent_scope=parent_scope,
    )
    setattr(viewset_class, lifecycle.restore_action_name, action_method)


def attach_bulk_actions(
    *,
    viewset_class: type[ModelViewSet],
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    bulk_actions: tuple[BulkActionSpec[Any], ...],
    bulk_action_serializers: dict[str, type[serializers.Serializer]],
    lifecycle: LifecycleConfig | None,
    acl: ACLConfig[M, Any, Any, Any] | None,
) -> None:
    """Attach generated bulk mutation endpoints to the ViewSet class."""
    for bulk_action in bulk_actions:
        action_method = build_bulk_action_method(
            create_input=create_input,
            update_input=update_input,
            partial_update_input=partial_update_input,
            create_handler=create_handler,
            update_handler=update_handler,
            partial_update_handler=partial_update_handler,
            bulk_action=bulk_action,
            serializer_class=bulk_action_serializers[bulk_action.name],
            lifecycle=lifecycle,
            acl=acl,
        )
        setattr(viewset_class, bulk_action.name, action_method)


def attach_field_subresources(
    *,
    viewset_class: type[ModelViewSet],
    model: type[M],
    field_subresources: tuple[FieldSubresourceSpec, ...],
    acl: ACLConfig[M, Any, Any, Any] | None,
    read_only: bool,
) -> None:
    """Attach generated single-field detail endpoints to the ViewSet class."""
    for field_subresource in field_subresources:
        action_method = build_field_subresource_method(
            model=model,
            field_subresource=field_subresource,
            acl=acl,
            read_only=read_only,
        )
        setattr(viewset_class, field_subresource.field_name, action_method)


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
        dto = validated_custom_action_dto(
            custom_action=custom_action,
            serializer_class=serializer_class,
            request=request,
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


def require_custom_action_dataclass(custom_action: CustomActionSpec[M]) -> type[object]:
    """Return the configured request dataclass for one custom action."""
    if custom_action.request_source == "query":
        if custom_action.query_dataclass is None:
            msg = f"Custom action {custom_action.name!r} is missing query_dataclass."
            raise TypeError(msg)
        return custom_action.query_dataclass
    if custom_action.input_dataclass is None:
        msg = f"Custom action {custom_action.name!r} is missing input_dataclass."
        raise TypeError(msg)
    return custom_action.input_dataclass


def validated_custom_action_dto(
    *,
    custom_action: CustomActionSpec[M],
    serializer_class: type[serializers.Serializer],
    request: Request,
) -> object:
    """Validate a custom action DTO from body or query params."""
    dataclass_type = require_custom_action_dataclass(custom_action)
    if custom_action.request_source == "query":
        return validated_query_dataclass(
            serializer_class=serializer_class,
            request=request,
            dataclass_type=dataclass_type,
        )
    return validated_input_dataclass(
        serializer_class=serializer_class,
        request=request,
        dataclass_type=dataclass_type,
    )


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


def build_restore_action_method(
    *,
    model: type[M],
    queryset: models.QuerySet[M],
    lifecycle: LifecycleConfig,
    lookup_field: str,
    lookup_url_kwarg: str | None,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
    acl: ACLConfig[M, Any, Any, Any] | None,
    parent_scope: ParentScopeSpec | None,
) -> Callable[..., Response]:
    """Build a generated restore detail action for lifecycle-managed resources."""

    def restore_action_method(
        self: ModelViewSet,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        scoped_queryset = queryset
        if parent_scope is not None:
            parent_lookup_value = self.kwargs[parent_scope.parent_lookup_url_kwarg]
            parent_instance = get_object_or_404(
                parent_scope.parent_model,
                **{parent_scope.parent_lookup_field: parent_lookup_value},
            )
            scoped_queryset = cast(
                models.QuerySet[M],
                scoped_queryset.filter(**{parent_scope.child_fk_field: parent_instance}),
            )
        lookup_name = lookup_url_kwarg or lookup_field
        instance = get_object_or_404(
            scoped_queryset,
            **{lookup_field: self.kwargs[lookup_name]},
        )
        enforce_instance_acl(
            request=request,
            acl=acl,
            action_config=acl_action(acl, "update_action"),
            instance=instance,
            resolver=resource_ref_from_instance(acl),
        )
        apply_restore_lifecycle(cast(models.Model, instance), lifecycle)
        return update_response(
            viewset=cast(Any, self),
            instance=instance,
            response_mapper=response_mapper,
            stat_specs=stat_specs,
            annotation_specs=annotation_specs,
        )

    restore_action_method.__name__ = lifecycle.restore_action_name
    restore_action_method.__qualname__ = lifecycle.restore_action_name
    restore_action_method.__doc__ = "Generated lifecycle restore action."
    return action(
        detail=True,
        methods=["post"],
        url_path=lifecycle.restore_url_path,
        url_name=lifecycle.restore_url_name,
    )(restore_action_method)


def build_bulk_action_method(
    *,
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    bulk_action: BulkActionSpec[Any],
    serializer_class: type[serializers.Serializer],
    lifecycle: LifecycleConfig | None,
    acl: ACLConfig[M, Any, Any, Any] | None,
) -> Callable[..., Response]:
    """Build one generated bulk mutation action method."""

    def bulk_action_method(
        self: ModelViewSet,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        input_dataclass = require_bulk_input_dataclass(
            bulk_action=bulk_action,
            create_input=create_input,
        )
        rows, row_errors = validated_bulk_rows(
            serializer_class=serializer_class,
            request=request,
            dataclass_type=input_dataclass,
            partial=bulk_action.kind == "patch",
            fill_missing_optional=bulk_action.kind == "patch",
        )
        if bulk_action.transaction_mode == "atomic" and row_errors:
            return bulk_result_response(
                result=BulkMutationResultDTO(
                    failed=len(row_errors),
                    rolled_back=True,
                    errors=row_errors,
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if bulk_action.transaction_mode == "atomic":
            try:
                with transaction.atomic():
                    result = apply_bulk_rows_atomically(
                        viewset=self,
                        request=request,
                        acl=acl,
                        bulk_action=bulk_action,
                        rows=rows,
                        create_handler=create_handler,
                        update_handler=update_handler,
                        partial_update_handler=partial_update_handler,
                        update_input=update_input,
                        partial_update_input=partial_update_input,
                        lifecycle=lifecycle,
                    )
            except BulkOperationAbort as exc:
                return bulk_result_response(
                    result=BulkMutationResultDTO(
                        failed=1,
                        rolled_back=True,
                        errors=[exc.row_error],
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            return bulk_result_response(
                result=result,
                status_code=bulk_success_status_code(bulk_action),
            )

        result = apply_bulk_rows_best_effort(
            viewset=self,
            request=request,
            acl=acl,
            bulk_action=bulk_action,
            rows=rows,
            initial_errors=row_errors,
            create_handler=create_handler,
            update_handler=update_handler,
            partial_update_handler=partial_update_handler,
            update_input=update_input,
            partial_update_input=partial_update_input,
            lifecycle=lifecycle,
        )
        return bulk_result_response(
            result=result,
            status_code=bulk_success_status_code(bulk_action, allow_partial=True),
        )

    bulk_action_method.__name__ = bulk_action.name
    bulk_action_method.__qualname__ = bulk_action.name
    bulk_action_method.__doc__ = f"Generated bulk mutation action `{bulk_action.name}`."
    return action(
        detail=False,
        methods=cast(Any, list(bulk_action.methods)),
        url_path=bulk_action.url_path,
        url_name=bulk_action.url_name,
    )(bulk_action_method)


class BulkOperationAbort(Exception):
    """Abort an atomic bulk operation after collecting one structured row error."""

    def __init__(self, row_error: BulkRowErrorDTO) -> None:
        super().__init__("bulk operation aborted")
        self.row_error = row_error


def validated_bulk_rows(
    *,
    serializer_class: type[serializers.Serializer],
    request: Request,
    dataclass_type: type[Any],
    partial: bool = False,
    fill_missing_optional: bool = False,
) -> tuple[list[tuple[int, Any]], list[BulkRowErrorDTO]]:
    """Validate a list request body one row at a time."""
    if not isinstance(request.data, list):
        return [], [
            BulkRowErrorDTO(
                index=0,
                identifier=None,
                errors=[
                    BulkFieldErrorDTO(
                        field="non_field_errors",
                        messages=["Expected a JSON list of objects."],
                    )
                ],
            )
        ]
    validated_rows: list[tuple[int, Any]] = []
    row_errors: list[BulkRowErrorDTO] = []
    for index, row_payload in enumerate(request.data):
        serializer = serializer_class(data=row_payload, partial=partial)
        if not serializer.is_valid():
            row_errors.append(
                BulkRowErrorDTO(
                    index=index,
                    identifier=identifier_from_raw_payload(row_payload),
                    errors=normalize_bulk_error_payload(serializer.errors),
                )
            )
            continue
        validated_rows.append(
            (
                index,
                serializer_to_dataclass(
                    serializer,
                    dataclass_type,
                    fill_missing_optional=fill_missing_optional,
                ),
            )
        )
    return validated_rows, row_errors


def apply_bulk_rows_atomically(
    *,
    viewset: ModelViewSet,
    request: Request,
    acl: ACLConfig[M, Any, Any, Any] | None,
    bulk_action: BulkActionSpec[Any],
    rows: list[tuple[int, Any]],
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    lifecycle: LifecycleConfig | None,
) -> BulkMutationResultDTO:
    """Apply every row inside one transaction, rolling back on the first failure."""
    result = empty_bulk_result()
    for index, dto in rows:
        row_result = apply_one_bulk_row(
            viewset=viewset,
            request=request,
            acl=acl,
            bulk_action=bulk_action,
            index=index,
            dto=dto,
            create_handler=create_handler,
            update_handler=update_handler,
            partial_update_handler=partial_update_handler,
            update_input=update_input,
            partial_update_input=partial_update_input,
            lifecycle=lifecycle,
        )
        if isinstance(row_result, BulkRowErrorDTO):
            raise BulkOperationAbort(row_result)
        merge_bulk_success(result, row_result)
    return result


def apply_bulk_rows_best_effort(
    *,
    viewset: ModelViewSet,
    request: Request,
    acl: ACLConfig[M, Any, Any, Any] | None,
    bulk_action: BulkActionSpec[Any],
    rows: list[tuple[int, Any]],
    initial_errors: list[BulkRowErrorDTO],
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    lifecycle: LifecycleConfig | None,
) -> BulkMutationResultDTO:
    """Apply valid rows while collecting row-level failures instead of aborting."""
    result = empty_bulk_result()
    result.errors.extend(initial_errors)
    result.failed += len(initial_errors)
    for index, dto in rows:
        row_result = apply_one_bulk_row(
            viewset=viewset,
            request=request,
            acl=acl,
            bulk_action=bulk_action,
            index=index,
            dto=dto,
            create_handler=create_handler,
            update_handler=update_handler,
            partial_update_handler=partial_update_handler,
            update_input=update_input,
            partial_update_input=partial_update_input,
            lifecycle=lifecycle,
        )
        if isinstance(row_result, BulkRowErrorDTO):
            result.failed += 1
            result.errors.append(row_result)
            continue
        merge_bulk_success(result, row_result)
    return result


def apply_one_bulk_row(
    *,
    viewset: ModelViewSet,
    request: Request,
    acl: ACLConfig[M, Any, Any, Any] | None,
    bulk_action: BulkActionSpec[Any],
    index: int,
    dto: Any,
    create_handler: CreateHandler[CreateDTO, M] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    lifecycle: LifecycleConfig | None,
) -> BulkMutationResultDTO | BulkRowErrorDTO:
    """Apply one validated bulk row and return either success counts or one row error."""
    try:
        if bulk_action.kind == "create":
            create_fn = require_write_handler(create_handler, "bulk_create")
            enforce_create_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "create_action"),
                dto=dto,
            )
            instance = create_fn(dto)
            return BulkMutationResultDTO(
                created=1,
                succeeded_identifiers=[instance_identifier_string(instance)],
            )

        instance = instance_for_bulk_row(
            queryset=viewset.get_queryset(),
            bulk_action=bulk_action,
            dto=dto,
        )

        if bulk_action.kind == "update":
            update_fn = require_write_handler(update_handler, "bulk_update")
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "update_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            update_dto = project_dataclass(
                dto,
                require_bulk_handler_dataclass(
                    bulk_action=bulk_action,
                    fallback_dataclass=update_input,
                    action_name="bulk_update",
                ),
            )
            enforce_target_update_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "update_action"),
                instance=instance,
                dto=update_dto,
                resolver=resource_ref_from_update_input(acl),
            )
            updated_instance = update_fn(instance, update_dto)
            return BulkMutationResultDTO(
                updated=1,
                succeeded_identifiers=[instance_identifier_string(updated_instance)],
            )

        if bulk_action.kind == "patch":
            patch_fn = require_write_handler(partial_update_handler, "bulk_patch")
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "partial_update_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            patch_dto = project_dataclass(
                dto,
                require_bulk_handler_dataclass(
                    bulk_action=bulk_action,
                    fallback_dataclass=partial_update_input,
                    action_name="bulk_patch",
                ),
                fill_missing_optional=True,
            )
            enforce_target_patch_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "partial_update_action"),
                instance=instance,
                dto=patch_dto,
                resolver=resource_ref_from_patch_input(acl),
            )
            updated_instance = patch_fn(instance, patch_dto)
            return BulkMutationResultDTO(
                updated=1,
                succeeded_identifiers=[instance_identifier_string(updated_instance)],
            )

        if bulk_action.kind == "delete":
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=acl_action(acl, "destroy_action"),
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            identifier = instance_identifier_string(instance)
            if lifecycle is None:
                viewset.perform_destroy(instance)
            else:
                apply_delete_lifecycle(cast(models.Model, instance), lifecycle)
            return BulkMutationResultDTO(
                deleted=1,
                succeeded_identifiers=[identifier],
            )
    except (ValidationError, PermissionDenied, NotFound) as exc:
        return bulk_row_error_from_exception(
            index=index,
            identifier=identifier_from_dto(dto, bulk_action.identifier_field),
            exc=exc,
        )

    raise ValueError(f"Unsupported bulk action kind {bulk_action.kind!r}.")


def require_bulk_input_dataclass(
    *,
    bulk_action: BulkActionSpec[Any],
    create_input: type[CreateDTO] | None,
) -> type[Any]:
    """Return the request row dataclass used by one bulk action."""
    if bulk_action.input_dataclass is not None:
        return bulk_action.input_dataclass
    if bulk_action.kind == "create" and create_input is not None:
        return cast(type[Any], create_input)
    raise TypeError(f"Bulk action {bulk_action.name!r} is missing input_dataclass.")


def require_bulk_handler_dataclass(
    *,
    bulk_action: BulkActionSpec[Any],
    fallback_dataclass: type[Any] | None,
    action_name: str,
) -> type[Any]:
    """Return the handler DTO type used after projecting a bulk row DTO."""
    if bulk_action.handler_dataclass is not None:
        return bulk_action.handler_dataclass
    if fallback_dataclass is not None:
        return fallback_dataclass
    raise TypeError(f"{action_name} requires a handler dataclass.")


def instance_for_bulk_row(
    *,
    queryset: models.QuerySet[M],
    bulk_action: BulkActionSpec[Any],
    dto: Any,
) -> M:
    """Return the target model instance for one update, patch, or delete row."""
    identifier_value = identifier_value_from_dto(dto, bulk_action.identifier_field)
    if identifier_value is None:
        raise ValidationError(
            {
                cast(str, bulk_action.identifier_field): [
                    "This field is required for bulk row identity."
                ]
            }
        )
    lookup_field = bulk_action.lookup_field
    if lookup_field is None:
        raise TypeError(f"Bulk action {bulk_action.name!r} is missing lookup_field.")
    lookup_kwargs = {lookup_field: identifier_value}
    try:
        return cast(M, queryset.get(**lookup_kwargs))
    except queryset.model.DoesNotExist as exc:
        raise NotFound("Target row was not found.") from exc


def identifier_value_from_dto(dto: Any, identifier_field: str | None) -> object:
    """Return the raw identifier value configured for one bulk row DTO."""
    if identifier_field is None or not hasattr(dto, identifier_field):
        return None
    return getattr(dto, identifier_field)


def identifier_from_dto(dto: Any, identifier_field: str | None) -> str | None:
    """Return a string identifier for docs/results when a DTO carries one."""
    identifier_value = identifier_value_from_dto(dto, identifier_field)
    if identifier_value is None:
        return None
    return str(identifier_value)


def identifier_from_raw_payload(payload: object) -> str | None:
    """Best-effort identifier extraction for invalid bulk row payloads."""
    if not isinstance(payload, dict):
        return None
    raw_identifier = payload.get("id")
    if raw_identifier is None:
        return None
    return str(raw_identifier)


def instance_identifier_string(instance: models.Model) -> str:
    """Return the primary-key identifier recorded in structured bulk results."""
    pk = instance.pk
    return "" if pk is None else str(pk)


def normalize_bulk_error_payload(payload: Any) -> list[BulkFieldErrorDTO]:
    """Convert DRF validation payloads into a stable typed bulk error shape."""
    if isinstance(payload, dict):
        return [
            BulkFieldErrorDTO(
                field=str(key),
                messages=[str(item) for item in ensure_error_list(value)],
            )
            for key, value in payload.items()
        ]
    return [
        BulkFieldErrorDTO(
            field="non_field_errors",
            messages=[str(item) for item in ensure_error_list(payload)],
        )
    ]


def ensure_error_list(value: Any) -> list[Any]:
    """Return a list representation for DRF validation error values."""
    if isinstance(value, list):
        return value
    return [value]


def bulk_row_error_from_exception(
    *,
    index: int,
    identifier: str | None,
    exc: ValidationError | PermissionDenied | NotFound,
) -> BulkRowErrorDTO:
    """Convert one DRF exception into a structured bulk row error DTO."""
    detail = getattr(exc, "detail", None)
    if detail is None:
        detail = str(exc)
    return BulkRowErrorDTO(
        index=index,
        identifier=identifier,
        errors=normalize_bulk_error_payload(detail),
    )


def empty_bulk_result() -> BulkMutationResultDTO:
    """Return an empty mutable-style bulk result dataclass."""
    return BulkMutationResultDTO()


def merge_bulk_success(
    target: BulkMutationResultDTO,
    source: BulkMutationResultDTO,
) -> None:
    """Accumulate one successful row result into a bulk result object."""
    target.created += source.created
    target.updated += source.updated
    target.deleted += source.deleted
    target.succeeded_identifiers.extend(source.succeeded_identifiers)


def bulk_success_status_code(
    bulk_action: BulkActionSpec[Any],
    *,
    allow_partial: bool = False,
) -> int:
    """Return the HTTP status code used by one successful bulk response."""
    if allow_partial:
        return status.HTTP_200_OK
    if bulk_action.kind == "create":
        return status.HTTP_201_CREATED
    return status.HTTP_200_OK


def bulk_result_response(
    *,
    result: BulkMutationResultDTO,
    status_code: int,
) -> Response:
    """Return a structured bulk operation response."""
    return Response(dataclass_instance_to_response_data(result), status=status_code)


def build_field_subresource_method(
    *,
    model: type[M],
    field_subresource: FieldSubresourceSpec,
    acl: ACLConfig[M, Any, Any, Any] | None,
    read_only: bool,
) -> Callable[..., Response]:
    """Build one generated detail endpoint over a single model field."""

    def field_subresource_method(
        self: ModelViewSet,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        instance = cast(M, self.get_object())
        request_method = (request.method or "").upper()
        if request_method == "GET":
            enforce_instance_acl(
                request=request,
                acl=acl,
                action_config=field_subresource.read_acl,
                instance=instance,
                resolver=resource_ref_from_instance(acl),
            )
            return Response(read_field_payload(instance, field_subresource.field_name))

        ensure_writes_are_allowed(read_only, "PATCH")
        enforce_instance_acl(
            request=request,
            acl=acl,
            action_config=field_subresource.patch_acl,
            instance=instance,
            resolver=resource_ref_from_instance(acl),
        )
        payload = validated_field_payload(
            model=model,
            field_name=field_subresource.field_name,
            payload=request.data,
        )
        updated_value = apply_field_subresource_patch(
            instance=instance,
            field_name=field_subresource.field_name,
            patch_mode=field_subresource.patch_mode,
            payload=payload,
        )
        return Response(updated_value)

    field_subresource_method.__name__ = field_subresource.field_name
    field_subresource_method.__qualname__ = field_subresource.field_name
    field_subresource_method.__doc__ = (
        f"Generated field subresource endpoint for `{field_subresource.field_name}` "
        f"({field_subresource_payload_label(model=model, field_name=field_subresource.field_name)})."
    )
    return action(
        detail=True,
        methods=cast(Any, list(field_subresource.methods)),
        url_path=field_subresource.url_path or field_subresource.field_name,
        url_name=field_subresource.url_name,
    )(field_subresource_method)


def http_method_names_for_mode(read_only: bool) -> list[str]:
    """Return allowed HTTP methods for the generated ViewSet mode."""
    if read_only:
        return ["get", "head", "options"]
    return ["get", "post", "put", "patch", "delete", "head", "options"]


def ensure_writes_are_allowed(read_only: bool, method: str) -> None:
    """Raise DRF's normal 405 error when a read-only factory receives a write."""
    if read_only:
        raise MethodNotAllowed(method)


def bind_parent_scope_to_dto(
    *,
    dto: Any,
    parent_scope: ParentScopeSpec | None,
    parent_instance: models.Model | None,
) -> Any:
    """Overwrite one DTO field with the parent object from the route.

    Parent-scoped endpoints must trust the URL over the request body.  This
    keeps nested create/update/patch endpoints constrained to the parent
    resource selected by the route and prevents clients from moving a child row
    under a different parent just by sending a conflicting foreign-key value.
    """
    if parent_scope is None or parent_instance is None or not parent_scope.bind_on_create:
        return dto
    binding_field_name = dataclass_parent_binding_field_name(
        dataclass_type=type(dto),
        child_fk_field=parent_scope.child_fk_field,
    )
    if binding_field_name is None:
        return dto
    override_value = parent_binding_value(
        dto=dto,
        binding_field_name=binding_field_name,
        child_fk_field=parent_scope.child_fk_field,
        parent_instance=parent_instance,
    )
    return override_dataclass(dto, {binding_field_name: override_value})


def parent_binding_value(
    *,
    dto: Any,
    binding_field_name: str,
    child_fk_field: str,
    parent_instance: models.Model,
) -> object:
    """Return the value that should be injected into one bound DTO field."""
    for dataclass_field in dataclass_fields(type(dto)):
        if dataclass_field.name != binding_field_name:
            continue
        mapped_name = cast(
            str,
            dataclass_field.metadata.get(MODEL_FIELD_METADATA_KEY, dataclass_field.name),
        )
        if mapped_name == f"{child_fk_field}_id":
            return parent_instance.pk
        return parent_instance
    return parent_instance


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
    annotation_specs: tuple[AnnotationSpec, ...],
) -> Response:
    """Return a DTO-shaped response for a list action, with pagination support."""
    page = viewset.paginate_queryset(cast(Any, queryset))
    if page is not None:
        data = response_data_for_many(page, response_mapper, stat_specs, annotation_specs)
        return viewset.get_paginated_response(data)

    data = response_data_for_many(queryset, response_mapper, stat_specs, annotation_specs)
    return Response(data)


def retrieve_response(
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> Response:
    """Return a DTO-shaped response for one object."""
    return Response(
        response_data_for_one(instance, response_mapper, stat_specs, annotation_specs)
    )


def create_response(
    *,
    viewset: ModelViewSet,
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> Response:
    """Return a DTO-shaped 201 response after a create hook succeeds."""
    response_instance = response_instance_with_stats(
        viewset=viewset,
        instance=instance,
        stat_specs=stat_specs,
        annotation_specs=annotation_specs,
    )
    return Response(
        response_data_for_one(
            response_instance,
            response_mapper,
            stat_specs,
            annotation_specs,
        ),
        status=status.HTTP_201_CREATED,
    )


def update_response(
    *,
    viewset: ModelViewSet,
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> Response:
    """Return a DTO-shaped 200 response after an update hook succeeds."""
    response_instance = response_instance_with_stats(
        viewset=viewset,
        instance=instance,
        stat_specs=stat_specs,
        annotation_specs=annotation_specs,
    )
    return Response(
        response_data_for_one(
            response_instance,
            response_mapper,
            stat_specs,
            annotation_specs,
        )
    )


def response_data_for_many(
    instances: Any,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> list[dict[str, Any]]:
    """Map every model instance in an iterable/queryset into response data."""
    return [
        response_data_for_one(instance, response_mapper, stat_specs, annotation_specs)
        for instance in instances
    ]


def response_data_for_one(
    instance: M,
    response_mapper: ResponseMapper[M, ResponseDTO],
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> dict[str, Any]:
    """Map one model instance into JSON-ready response data."""
    return map_instance_to_response_data(
        instance,
        response_mapper,
        stat_specs,
        annotation_specs,
    )


def response_instance_with_stats(
    *,
    viewset: ModelViewSet,
    instance: M,
    stat_specs: tuple[AggregateStatSpec, ...],
    annotation_specs: tuple[AnnotationSpec, ...],
) -> M:
    """Reload write-hook results so create/update responses include fresh stats."""
    response_instance = instance_with_stat_annotations(
        instance=instance,
        queryset=viewset.get_queryset(),
        stat_specs=stat_specs,
    )
    return instance_with_annotation_specs(
        instance=response_instance,
        queryset=viewset.get_queryset(),
        annotation_specs=annotation_specs,
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
