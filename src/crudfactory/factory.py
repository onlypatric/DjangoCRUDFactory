from __future__ import annotations

from typing import Any, Generic, Sequence, TypeVar, cast

from django.db import models
from django.urls.resolvers import URLPattern, URLResolver
from rest_framework.authentication import BaseAuthentication
from rest_framework.pagination import BasePagination
from rest_framework.permissions import BasePermission
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ModelViewSet

from .acl import ACLConfig
from .actions import CustomActionSpec, GroupedCollectionActionSpec
from .annotations import (
    annotate_queryset_with_annotation_specs,
    annotation_specs_from_response_mapper,
    instance_with_annotation_specs,
)
from ._auto_response import build_auto_response_mapper, build_declared_response_mapper
from .bulk_actions import BulkActionSpec
from .filters import FilterSpec, filter_specs_from_response_mapper
from .field_subresources import (
    FieldSubresourceSpec,
    normalize_field_subresources,
)
from .ordering import OrderSpec, order_specs_from_response_mapper
from .markdown_docs import render_factory_markdown
from ._nested_writes import (
    NestedWriteSpec,
    nested_field_names,
    normalize_nested_writes,
    wrap_create_handler_with_nested_writes,
    wrap_update_handler_with_nested_writes,
)
from .response import map_instance_to_response_data, map_instance_to_response_dataclass
from .routers import build_app_urlconf, build_router, router_urlpatterns
from ._simple_writes import (
    build_simple_create_handler,
    build_simple_partial_update_handler,
    build_simple_update_handler,
    writable_field_names_from_dataclass,
)
from .stats import (
    AggregateStatSpec,
    instance_with_stat_annotations,
    stat_specs_from_response_mapper,
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
from .validation import validate_factory_configuration
from .viewsets import build_crud_viewset_class

__all__ = ["CRUDFactory"]


class CRUDFactory(Generic[M, CreateDTO, UpdateDTO, PatchDTO, ResponseDTO]):
    """Generate typed Django REST Framework CRUD endpoints.

    CRUDFactory is intentionally small at the public API level.  A caller gives
    it a primary Django model, request DTO dataclasses, and a response DTO
    mapper.  Simple CRUD writes can be generated from an explicit
    `writable_fields` allowlist, while complex writes can still go through
    user-provided hooks.  The factory then creates a DRF `ModelViewSet` and
    router/url helpers that can be mounted inside a normal Django app.
    """

    def __init__(
        self,
        model: type[M],
        response_mapper: ResponseMapper[M, ResponseDTO] | None = None,
        response_dataclass: type[ResponseDTO] | None = None,
        *,
        create_input: type[CreateDTO] | None = None,
        update_input: type[UpdateDTO] | None = None,
        partial_update_input: type[PatchDTO] | None = None,
        create_handler: CreateHandler[CreateDTO, M] | None = None,
        update_handler: UpdateHandler[M, UpdateDTO] | None = None,
        partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None = None,
        writable_fields: Sequence[str] | None = None,
        nested_writes: Sequence[NestedWriteSpec] | None = None,
        field_subresources: Sequence[FieldSubresourceSpec] | None = None,
        custom_actions: Sequence[CustomActionSpec[M]] | None = None,
        grouped_actions: Sequence[GroupedCollectionActionSpec[M]] | None = None,
        bulk_actions: Sequence[BulkActionSpec[Any]] | None = None,
        acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None = None,
        read_only: bool = False,
        app_name: str | None = None,
        route: str | None = None,
        basename: str | None = None,
        queryset: models.QuerySet[M] | None = None,
        lookup_field: str = "pk",
        lookup_url_kwarg: str | None = None,
        permission_classes: Sequence[type[BasePermission]] | None = None,
        authentication_classes: Sequence[type[BaseAuthentication]] | None = None,
        pagination_class: type[BasePagination] | None = None,
    ) -> None:
        """Store the CRUD contract and validate it immediately."""
        self.model = model
        self.create_input = create_input
        self.update_input = update_input
        self.partial_update_input = partial_update_input
        self.response_mapper: ResponseMapper[M, ResponseDTO] = resolve_response_mapper(
            model=model,
            response_mapper=response_mapper,
            response_dataclass=response_dataclass,
            update_input=update_input,
        )
        self.writable_fields: tuple[str, ...] | None = normalize_writable_fields(
            writable_fields
        )
        self.nested_writes: tuple[NestedWriteSpec, ...] = normalize_nested_writes(
            nested_writes
        )
        self.field_subresources: tuple[FieldSubresourceSpec, ...] = (
            normalize_field_subresources(field_subresources)
        )
        self.create_handler = resolve_create_handler(
            model=model,
            create_input=create_input,
            create_handler=create_handler,
            writable_fields=self.writable_fields,
            nested_writes=self.nested_writes,
            read_only=read_only,
        )
        self.update_handler = resolve_update_handler(
            model=model,
            update_input=update_input,
            update_handler=update_handler,
            writable_fields=self.writable_fields,
            nested_writes=self.nested_writes,
            read_only=read_only,
        )
        self.partial_update_handler = resolve_partial_update_handler(
            model=model,
            partial_update_input=partial_update_input,
            partial_update_handler=partial_update_handler,
            writable_fields=self.writable_fields,
            nested_writes=self.nested_writes,
            read_only=read_only,
        )
        self.custom_actions: tuple[CustomActionSpec[M], ...] = normalize_custom_actions(
            custom_actions
        )
        self.grouped_actions: tuple[GroupedCollectionActionSpec[M], ...] = (
            normalize_grouped_actions(grouped_actions)
        )
        self.bulk_actions: tuple[BulkActionSpec[Any], ...] = normalize_bulk_actions(
            bulk_actions
        )
        self.acl = acl
        self.is_read_only = read_only
        self.app_name: str = resolve_app_name(model, app_name)
        self.route: str = resolve_route(model, route)
        self.basename: str = resolve_basename(model, basename)
        self.queryset = queryset
        self.lookup_field = lookup_field
        self.lookup_url_kwarg = lookup_url_kwarg
        self.permission_classes: tuple[type[BasePermission], ...] | None = (
            normalize_class_sequence(permission_classes)
        )
        self.authentication_classes: tuple[type[BaseAuthentication], ...] | None = (
            normalize_class_sequence(authentication_classes)
        )
        self.pagination_class = pagination_class
        self.filter_specs: tuple[FilterSpec, ...] = filter_specs_from_response_mapper(
            self.response_mapper
        )
        self.order_specs: tuple[OrderSpec, ...] = order_specs_from_response_mapper(
            self.response_mapper
        )
        self.stat_specs: tuple[AggregateStatSpec, ...] = stat_specs_from_response_mapper(
            self.response_mapper
        )
        self.annotation_specs = annotation_specs_from_response_mapper(
            self.model,
            self.response_mapper
        )

        self.validate_configuration()

    def validate_configuration(self) -> None:
        """Validate the factory configuration once at construction time."""
        validate_factory_configuration(
            model=self.model,
            response_mapper=self.response_mapper,
            create_input=self.create_input,
            update_input=self.update_input,
            partial_update_input=self.partial_update_input,
            create_handler=self.create_handler,
            update_handler=self.update_handler,
            partial_update_handler=self.partial_update_handler,
            nested_writes=self.nested_writes,
            field_subresources=self.field_subresources,
            custom_actions=self.custom_actions,
            grouped_actions=self.grouped_actions,
            bulk_actions=self.bulk_actions,
            acl=self.acl,
            app_name=self.app_name,
            route=self.route,
            basename=self.basename,
            read_only=self.is_read_only,
        )

    def get_viewset_class(self) -> type[ModelViewSet]:
        """Return a generated DRF ModelViewSet class for router registration."""
        return build_crud_viewset_class(
            model=self.model,
            response_mapper=self.response_mapper,
            create_input=self.create_input,
            update_input=self.update_input,
            partial_update_input=self.partial_update_input,
            create_handler=self.create_handler,
            update_handler=self.update_handler,
            partial_update_handler=self.partial_update_handler,
            custom_actions=self.custom_actions,
            grouped_actions=self.grouped_actions,
            bulk_actions=self.bulk_actions,
            field_subresources=self.field_subresources,
            acl=self.acl,
            read_only=self.is_read_only,
            queryset=self.queryset,
            lookup_field=self.lookup_field,
            lookup_url_kwarg=self.lookup_url_kwarg,
            permission_classes=self.permission_classes,
            authentication_classes=self.authentication_classes,
            pagination_class=self.pagination_class,
            filter_specs=self.filter_specs,
            order_specs=self.order_specs,
            stat_specs=self.stat_specs,
            annotation_specs=self.annotation_specs,
        )

    @classmethod
    def read_only(
        cls,
        model: type[M],
        response_mapper: ResponseMapper[M, ResponseDTO] | None = None,
        *,
        response_dataclass: type[ResponseDTO] | None = None,
        app_name: str | None = None,
        route: str | None = None,
        basename: str | None = None,
        queryset: models.QuerySet[M] | None = None,
        lookup_field: str = "pk",
        lookup_url_kwarg: str | None = None,
        permission_classes: Sequence[type[BasePermission]] | None = None,
        authentication_classes: Sequence[type[BaseAuthentication]] | None = None,
        pagination_class: type[BasePagination] | None = None,
        custom_actions: Sequence[CustomActionSpec[M]] | None = None,
        grouped_actions: Sequence[GroupedCollectionActionSpec[M]] | None = None,
        bulk_actions: Sequence[BulkActionSpec[Any]] | None = None,
        field_subresources: Sequence[FieldSubresourceSpec] | None = None,
        acl: ACLConfig[M, object, object, object] | None = None,
    ) -> CRUDFactory[M, object, object, object, ResponseDTO]:
        """Return a factory that exposes only list and retrieve endpoints."""
        return CRUDFactory(
            model=model,
            response_mapper=response_mapper,
            response_dataclass=response_dataclass,
            read_only=True,
            app_name=app_name,
            route=route,
            basename=basename,
            queryset=queryset,
            lookup_field=lookup_field,
            lookup_url_kwarg=lookup_url_kwarg,
            permission_classes=permission_classes,
            authentication_classes=authentication_classes,
            pagination_class=pagination_class,
            custom_actions=custom_actions,
            grouped_actions=grouped_actions,
            bulk_actions=bulk_actions,
            field_subresources=field_subresources,
            acl=acl,
        )

    def get_router(
        self,
        *,
        route: str | None = None,
        basename: str | None = None,
        router_class: type[SimpleRouter] = SimpleRouter,
    ) -> SimpleRouter:
        """Return a DRF router with the generated ViewSet already registered."""
        return build_router(
            viewset_class=self.get_viewset_class(),
            route=resolve_override(route, self.route),
            basename=resolve_override(basename, self.basename),
            router_class=router_class,
        )

    def get_urlpatterns(
        self,
        *,
        route: str | None = None,
        basename: str | None = None,
        router_class: type[SimpleRouter] = SimpleRouter,
    ) -> list[URLPattern | URLResolver]:
        """Return urlpatterns suitable for a Django app's `urls.py` file."""
        router = self.get_router(
            route=route,
            basename=basename,
            router_class=router_class,
        )
        return router_urlpatterns(router)

    def get_app_urlconf(
        self,
        *,
        route: str | None = None,
        basename: str | None = None,
        namespace: str | None = None,
        router_class: type[SimpleRouter] = SimpleRouter,
    ) -> tuple[list[URLPattern | URLResolver], str, str]:
        """Return an include-ready `(urlpatterns, app_name, namespace)` tuple."""
        urlpatterns = self.get_urlpatterns(
            route=route,
            basename=basename,
            router_class=router_class,
        )
        return build_app_urlconf(
            urlpatterns=urlpatterns,
            app_name=self.app_name,
            namespace=resolve_namespace(namespace, self.app_name),
        )

    def to_dataclass(self, instance: M) -> ResponseDTO:
        """Return the response DTO for one model instance."""
        return map_instance_to_response_dataclass(instance, self.response_mapper)

    def to_response_data(self, instance: M) -> dict[str, object]:
        """Return JSON-ready response data for one model instance."""
        response_instance = instance_with_stat_annotations(
            instance=instance,
            queryset=annotate_queryset_with_annotation_specs(
                queryset_for_factory_method(self.model, self.queryset),
                self.annotation_specs,
            ),
            stat_specs=self.stat_specs,
        )
        response_instance = instance_with_annotation_specs(
            instance=response_instance,
            queryset=queryset_for_factory_method(self.model, self.queryset),
            annotation_specs=self.annotation_specs,
        )
        return map_instance_to_response_data(
            response_instance,
            self.response_mapper,
            self.stat_specs,
            self.annotation_specs,
        )

    def render_markdown_docs(
        self,
        *,
        title: str | None = None,
        base_path: str = "/api",
    ) -> str:
        """Return a Markdown contract document for this generated factory."""
        return render_factory_markdown(self, title=title, base_path=base_path)


def resolve_app_name(model: type[models.Model], configured_app_name: str | None) -> str:
    """Return the configured app name or the model's Django app label."""
    if configured_app_name is not None:
        return configured_app_name
    return model._meta.app_label


def resolve_route(model: type[models.Model], configured_route: str | None) -> str:
    """Return the configured router route or a model-derived default."""
    return resolve_model_name_default(model, configured_route)


def resolve_basename(model: type[models.Model], configured_basename: str | None) -> str:
    """Return the configured router basename or a model-derived default."""
    return resolve_model_name_default(model, configured_basename)


def resolve_model_name_default(
    model: type[models.Model],
    configured_value: str | None,
) -> str:
    """Use Django's model_name, falling back to the Python class name."""
    if configured_value is not None:
        return configured_value
    return model._meta.model_name or model.__name__.lower()


def resolve_override(configured_value: str | None, default_value: str) -> str:
    """Return an optional method-level override or the factory default."""
    if configured_value is not None:
        return configured_value
    return default_value


def resolve_namespace(configured_namespace: str | None, app_name: str) -> str:
    """Return an include namespace, defaulting to the app name."""
    return resolve_override(configured_namespace, app_name)


ClassT = TypeVar("ClassT")


def normalize_class_sequence(
    classes: Sequence[type[ClassT]] | None,
) -> tuple[type[ClassT], ...] | None:
    """Freeze optional DRF class sequences so generated ViewSets are stable."""
    if classes is None:
        return None
    return tuple(classes)


def normalize_custom_actions(
    custom_actions: Sequence[CustomActionSpec[M]] | None,
) -> tuple[CustomActionSpec[M], ...]:
    """Freeze optional custom action specs for generated ViewSet stability."""
    if custom_actions is None:
        return ()
    return tuple(custom_actions)


def normalize_grouped_actions(
    grouped_actions: Sequence[GroupedCollectionActionSpec[M]] | None,
) -> tuple[GroupedCollectionActionSpec[M], ...]:
    """Freeze optional grouped action specs for generated ViewSet stability."""
    if grouped_actions is None:
        return ()
    return tuple(grouped_actions)


def normalize_bulk_actions(
    bulk_actions: Sequence[BulkActionSpec[Any]] | None,
) -> tuple[BulkActionSpec[Any], ...]:
    """Freeze optional bulk action specs for generated ViewSet stability."""
    if bulk_actions is None:
        return ()
    return tuple(bulk_actions)


def normalize_writable_fields(
    writable_fields: Sequence[str] | None,
) -> tuple[str, ...] | None:
    """Freeze optional simple-write field names for stable generated handlers."""
    if writable_fields is None:
        return None
    return tuple(writable_fields)


def resolve_create_handler(
    *,
    model: type[M],
    create_input: type[CreateDTO] | None,
    create_handler: CreateHandler[CreateDTO, M] | None,
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
    read_only: bool,
) -> CreateHandler[CreateDTO, M] | None:
    """Return an explicit create hook or generate one from writable_fields."""
    if create_handler is not None or read_only:
        if create_handler is None or create_input is None or not nested_writes:
            return create_handler
        return wrap_create_handler_with_nested_writes(
            model=model,
            dataclass_type=create_input,
            create_handler=create_handler,
            nested_writes=nested_writes,
        )
    if create_input is None:
        return None
    root_handler = auto_create_handler(
        model=model,
        create_input=create_input,
        writable_fields=writable_fields,
        nested_writes=nested_writes,
    )
    if not nested_writes:
        return root_handler
    return wrap_create_handler_with_nested_writes(
        model=model,
        dataclass_type=create_input,
        create_handler=root_handler,
        nested_writes=nested_writes,
    )


def resolve_update_handler(
    *,
    model: type[M],
    update_input: type[UpdateDTO] | None,
    update_handler: UpdateHandler[M, UpdateDTO] | None,
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
    read_only: bool,
) -> UpdateHandler[M, UpdateDTO] | None:
    """Return an explicit update hook or generate one from writable_fields."""
    if update_handler is not None or read_only:
        if update_handler is None or update_input is None or not nested_writes:
            return update_handler
        return wrap_update_handler_with_nested_writes(
            model=model,
            dataclass_type=update_input,
            update_handler=update_handler,
            nested_writes=nested_writes,
            partial=False,
        )
    if update_input is None:
        return None
    root_handler = auto_update_handler(
        model=model,
        update_input=update_input,
        writable_fields=writable_fields,
        nested_writes=nested_writes,
    )
    if not nested_writes:
        return root_handler
    return wrap_update_handler_with_nested_writes(
        model=model,
        dataclass_type=update_input,
        update_handler=root_handler,
        nested_writes=nested_writes,
        partial=False,
    )


def resolve_partial_update_handler(
    *,
    model: type[M],
    partial_update_input: type[PatchDTO] | None,
    partial_update_handler: PartialUpdateHandler[M, PatchDTO] | None,
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
    read_only: bool,
) -> PartialUpdateHandler[M, PatchDTO] | None:
    """Return an explicit PATCH hook or generate one from writable_fields."""
    if partial_update_handler is not None or read_only:
        if partial_update_handler is None or partial_update_input is None or not nested_writes:
            return partial_update_handler
        return wrap_update_handler_with_nested_writes(
            model=model,
            dataclass_type=partial_update_input,
            update_handler=partial_update_handler,
            nested_writes=nested_writes,
            partial=True,
        )
    if partial_update_input is None:
        return None
    root_handler = auto_partial_update_handler(
        model=model,
        partial_update_input=partial_update_input,
        writable_fields=writable_fields,
        nested_writes=nested_writes,
    )
    if not nested_writes:
        return root_handler
    return wrap_update_handler_with_nested_writes(
        model=model,
        dataclass_type=partial_update_input,
        update_handler=root_handler,
        nested_writes=nested_writes,
        partial=True,
    )


def auto_create_handler(
    *,
    model: type[M],
    create_input: type[CreateDTO],
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
) -> CreateHandler[CreateDTO, M]:
    """Build the generated root create handler, excluding nested write fields."""
    root_writable_fields = root_writable_field_names(
        dataclass_type=create_input,
        writable_fields=writable_fields,
        nested_writes=nested_writes,
    )
    if not root_writable_fields:
        return create_instance_with_defaults(model)
    return build_simple_create_handler(
        model=model,
        dataclass_type=create_input,
        writable_fields=root_writable_fields,
    )


def auto_update_handler(
    *,
    model: type[M],
    update_input: type[UpdateDTO],
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
) -> UpdateHandler[M, UpdateDTO]:
    """Build the generated root update handler, excluding nested write fields."""
    root_writable_fields = root_writable_field_names(
        dataclass_type=update_input,
        writable_fields=writable_fields,
        nested_writes=nested_writes,
    )
    if not root_writable_fields:
        return return_instance_unchanged
    return build_simple_update_handler(
        model=model,
        dataclass_type=update_input,
        writable_fields=root_writable_fields,
    )


def auto_partial_update_handler(
    *,
    model: type[M],
    partial_update_input: type[PatchDTO],
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
) -> PartialUpdateHandler[M, PatchDTO]:
    """Build the generated PATCH handler, excluding nested write fields."""
    root_writable_fields = root_writable_field_names(
        dataclass_type=partial_update_input,
        writable_fields=writable_fields,
        nested_writes=nested_writes,
    )
    if not root_writable_fields:
        return return_instance_unchanged
    return build_simple_partial_update_handler(
        model=model,
        dataclass_type=partial_update_input,
        writable_fields=root_writable_fields,
    )


def root_writable_field_names(
    *,
    dataclass_type: type[object],
    writable_fields: tuple[str, ...] | None,
    nested_writes: tuple[NestedWriteSpec, ...],
) -> tuple[str, ...]:
    """Return root-model writable fields after excluding nested relation DTO fields."""
    nested_names = nested_field_names(nested_writes)
    configured_fields = writable_fields
    if configured_fields is None:
        configured_fields = writable_field_names_from_dataclass(dataclass_type)
    return tuple(field_name for field_name in configured_fields if field_name not in nested_names)


def create_instance_with_defaults(model: type[M]) -> CreateHandler[Any, M]:
    """Return a create handler that relies entirely on model defaults."""
    def create_instance(_dto: Any) -> M:
        return cast(M, model._default_manager.create())

    return create_instance


def return_instance_unchanged(instance: M, _dto: Any) -> M:
    """Return the existing instance when only nested relations are being handled."""
    return instance


def resolve_response_mapper(
    *,
    model: type[M],
    response_mapper: ResponseMapper[M, ResponseDTO] | None,
    response_dataclass: type[ResponseDTO] | None,
    update_input: type[object] | None,
) -> ResponseMapper[M, ResponseDTO]:
    """Return an explicit mapper or generate one from the configured contract."""
    if response_mapper is not None:
        return response_mapper
    if response_dataclass is not None:
        return cast(
            ResponseMapper[M, ResponseDTO],
            build_declared_response_mapper(
                model=model,
                response_dataclass=response_dataclass,
            ),
        )
    if update_input is None:
        msg = (
            "response_mapper is required when neither response_dataclass nor "
            "update_input is configured."
        )
        raise TypeError(msg)
    return cast(
        ResponseMapper[M, ResponseDTO],
        build_auto_response_mapper(model=model, source_dataclass=update_input),
    )


def queryset_for_factory_method(
    model: type[M],
    queryset: models.QuerySet[M] | None,
) -> models.QuerySet[M]:
    """Return the queryset used by factory helper methods outside a ViewSet."""
    if queryset is not None:
        return queryset
    return model.objects.all()
