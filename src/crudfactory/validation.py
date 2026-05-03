from __future__ import annotations

from dataclasses import is_dataclass
from typing import cast, get_type_hints

from django.db import models

from .acl import ACLConfig
from .actions import (
    CustomActionSpec,
    GroupedCollectionActionSpec,
    GroupedCollectionSourceACL,
)
from .bulk_actions import BulkActionSpec
from ._nested_writes import NestedWriteSpec, validate_nested_write_dataclass
from .dataclass_serializers import (
    ensure_dataclass_type,
    validate_partial_update_dataclass,
    validate_supported_dataclass_fields,
)
from .field_subresources import FieldSubresourceSpec, validate_field_subresources
from .list_queries import (
    list_query_filter_specs_from_dataclass,
    list_query_ordering_specs_from_dataclass,
    list_query_search_specs_from_dataclass,
)
from .parent_scopes import ParentScopeSpec, validate_parent_scope
from .schema import validate_supported_response_dataclass_fields
from .source_queries import (
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


def validate_factory_configuration(
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
    nested_writes: tuple[NestedWriteSpec, ...],
    field_subresources: tuple[FieldSubresourceSpec, ...],
    custom_actions: tuple[CustomActionSpec[M], ...],
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
    bulk_actions: tuple[BulkActionSpec[object], ...],
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    app_name: str,
    route: str,
    basename: str,
    read_only: bool,
    parent_scope: ParentScopeSpec | None,
) -> None:
    """Validate every user-supplied piece of a CRUDFactory.

    The factory is usually instantiated from a Django app module such as
    `api.py` or `urls.py`.  That means invalid configuration should fail during
    startup or test import, not halfway through handling a request.
    """
    validate_model_class(model)
    validate_callable("response_mapper", response_mapper)
    validate_response_mapper_dataclass(response_mapper)
    validate_custom_actions(custom_actions)
    validate_grouped_actions(grouped_actions)
    validate_list_query(list_query)
    validate_bulk_actions(
        create_input=create_input,
        update_input=update_input,
        partial_update_input=partial_update_input,
        bulk_actions=bulk_actions,
        read_only=read_only,
    )
    validate_acl_configuration(acl, custom_actions, grouped_actions)
    validate_field_subresources(
        model=model,
        field_subresources=field_subresources,
        read_only=read_only,
    )
    validate_parent_scope(
        model=model,
        parent_scope_spec=parent_scope,
        create_input=cast(type[object] | None, create_input),
        update_input=cast(type[object] | None, update_input),
        partial_update_input=cast(type[object] | None, partial_update_input),
        read_only=read_only,
    )
    validate_non_empty_string("app_name", app_name)
    validate_non_empty_string("route", route)
    validate_non_empty_string("basename", basename)
    if read_only:
        return

    validate_required_value("create_input", create_input)
    validate_required_value("update_input", update_input)
    validate_required_value("partial_update_input", partial_update_input)
    validate_callable("create_handler", create_handler)
    validate_callable("update_handler", update_handler)
    validate_callable("partial_update_handler", partial_update_handler)
    create_dataclass = cast(type[object], create_input)
    update_dataclass = cast(type[object], update_input)
    validate_input_dataclass("create_input", create_dataclass)
    validate_input_dataclass("update_input", update_dataclass)
    patch_input = cast(type[object], partial_update_input)
    validate_input_dataclass("partial_update_input", patch_input)
    validate_nested_write_dataclass(
        model=model,
        dataclass_type=create_dataclass,
        nested_writes=nested_writes,
        action_name="create_input",
        partial=False,
    )
    validate_nested_write_dataclass(
        model=model,
        dataclass_type=update_dataclass,
        nested_writes=nested_writes,
        action_name="update_input",
        partial=False,
    )
    validate_nested_write_dataclass(
        model=model,
        dataclass_type=patch_input,
        nested_writes=nested_writes,
        action_name="partial_update_input",
        partial=True,
    )
    validate_partial_update_dataclass(patch_input)


def validate_model_class(model: type[object]) -> None:
    """Ensure the primary model is a Django model class."""
    if not isinstance(model, type) or not issubclass(model, models.Model):
        msg = "model must be a Django model class."
        raise TypeError(msg)


def validate_callable(name: str, value: object) -> None:
    """Ensure a hook or mapper is callable."""
    if not callable(value):
        msg = f"{name} is required and must be callable."
        raise TypeError(msg)


def validate_required_value(name: str, value: object) -> None:
    """Ensure a required full-CRUD component was configured."""
    if value is None:
        msg = f"{name} is required unless read_only=True."
        raise TypeError(msg)


def validate_non_empty_string(name: str, value: str) -> None:
    """Ensure a generated URL naming component is usable."""
    if not value:
        msg = f"{name} must be a non-empty string."
        raise ValueError(msg)


def validate_input_dataclass(name: str, dataclass_type: type[object]) -> None:
    """Validate a request DTO dataclass and every field it declares."""
    ensure_dataclass_type(name, dataclass_type)
    validate_supported_dataclass_fields(dataclass_type)


def validate_list_query(list_query: type[object] | None) -> None:
    """Validate an advanced list query DTO and its metadata declarations."""
    if list_query is None:
        return
    validate_input_dataclass("list_query", list_query)
    list_query_filter_specs_from_dataclass(list_query)
    list_query_search_specs_from_dataclass(list_query)
    list_query_ordering_specs_from_dataclass(list_query)


def validate_response_mapper_dataclass(
    response_mapper: ResponseMapper[M, ResponseDTO],
) -> None:
    """Validate the response mapper's dataclass return contract eagerly."""
    response_dataclass = required_response_dataclass_from_mapper(response_mapper)
    validate_supported_response_dataclass_fields(response_dataclass)


def required_response_dataclass_from_mapper(
    response_mapper: ResponseMapper[M, ResponseDTO],
) -> type[object]:
    """Return the mapper's response dataclass annotation or raise clearly."""
    type_hints = get_type_hints(response_mapper)
    if "return" not in type_hints:
        msg = (
            "response_mapper must declare a dataclass return annotation, "
            "for example `def to_response(instance: Model) -> ResponseDTO:`."
        )
        raise TypeError(msg)

    return_type = type_hints["return"]
    if isinstance(return_type, type) and is_dataclass(return_type):
        return return_type

    msg = (
        "response_mapper return annotation must be a dataclass type. "
        f"Got {return_type!r}."
    )
    raise TypeError(msg)


def validate_custom_actions(
    custom_actions: tuple[CustomActionSpec[M], ...],
) -> None:
    """Validate typed custom action input and response dataclasses."""
    seen_names: set[str] = set()
    for custom_action in custom_actions:
        validate_non_empty_string("custom action name", custom_action.name)
        if custom_action.name in seen_names:
            msg = f"Duplicate custom action name {custom_action.name!r}."
            raise ValueError(msg)
        seen_names.add(custom_action.name)
        validate_custom_action_request_contract(custom_action)
        validate_supported_response_dataclass_fields(custom_action.response_dataclass)
        validate_callable(f"custom action {custom_action.name} handler", custom_action.handler)
        validate_custom_action_methods(custom_action)


def validate_custom_action_request_contract(
    custom_action: CustomActionSpec[M],
) -> None:
    """Validate whether a custom action is body-driven or query-driven."""
    if custom_action.request_source == "body":
        if custom_action.input_dataclass is None or custom_action.query_dataclass is not None:
            msg = (
                f"Custom action {custom_action.name!r} must define input_dataclass "
                "and no query_dataclass when request_source='body'."
            )
            raise TypeError(msg)
        validate_input_dataclass(
            f"custom action {custom_action.name} input_dataclass",
            custom_action.input_dataclass,
        )
        return
    if custom_action.request_source == "query":
        if custom_action.input_dataclass is not None or custom_action.query_dataclass is None:
            msg = (
                f"Custom action {custom_action.name!r} must define query_dataclass "
                "and no input_dataclass when request_source='query'."
            )
            raise TypeError(msg)
        validate_input_dataclass(
            f"custom action {custom_action.name} query_dataclass",
            custom_action.query_dataclass,
        )
        return
    msg = f"Unsupported request_source {custom_action.request_source!r}."
    raise ValueError(msg)


def validate_custom_action_methods(custom_action: CustomActionSpec[M]) -> None:
    """Keep query-driven collection actions within the intended GET-only surface."""
    if custom_action.request_source != "query":
        return
    if custom_action.detail:
        msg = (
            f"Query-driven custom action {custom_action.name!r} must be a "
            "collection action."
        )
        raise ValueError(msg)
    if tuple(custom_action.methods) != ("get",):
        msg = (
            f"Query-driven custom action {custom_action.name!r} only supports "
            "methods=('get',) in v1."
        )
        raise ValueError(msg)


def validate_grouped_actions(
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
) -> None:
    """Validate grouped action query/response contracts and methods."""
    seen_names: set[str] = set()
    for grouped_action in grouped_actions:
        validate_non_empty_string("grouped action name", grouped_action.name)
        if grouped_action.name in seen_names:
            msg = f"Duplicate grouped action name {grouped_action.name!r}."
            raise ValueError(msg)
        seen_names.add(grouped_action.name)
        validate_input_dataclass(
            f"grouped action {grouped_action.name} query_dataclass",
            grouped_action.query_dataclass,
        )
        validate_supported_response_dataclass_fields(grouped_action.response_dataclass)
        validate_callable(
            f"grouped action {grouped_action.name} handler",
            grouped_action.handler,
        )
        validate_grouped_action_methods(grouped_action)
        source_filter_specs_from_dataclass(grouped_action.query_dataclass)
        source_order_specs_from_dataclass(grouped_action.query_dataclass)
        validate_grouped_action_source_acl(grouped_action.source_acl)


def validate_bulk_actions(
    *,
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    bulk_actions: tuple[BulkActionSpec[object], ...],
    read_only: bool,
) -> None:
    """Validate generated bulk mutation action contracts."""
    if read_only and bulk_actions:
        raise TypeError("Bulk actions cannot be used on read_only factories.")
    seen_names: set[str] = set()
    for bulk_action in bulk_actions:
        validate_non_empty_string("bulk action name", bulk_action.name)
        if bulk_action.name in seen_names:
            msg = f"Duplicate bulk action name {bulk_action.name!r}."
            raise ValueError(msg)
        seen_names.add(bulk_action.name)
        validate_bulk_action_contract(
            create_input=create_input,
            update_input=update_input,
            partial_update_input=partial_update_input,
            bulk_action=bulk_action,
        )


def validate_bulk_action_contract(
    *,
    create_input: type[CreateDTO] | None,
    update_input: type[UpdateDTO] | None,
    partial_update_input: type[PatchDTO] | None,
    bulk_action: BulkActionSpec[object],
) -> None:
    """Validate one bulk action against the enclosing factory write DTOs."""
    if bulk_action.kind == "create":
        effective_input = bulk_action.input_dataclass or create_input
        if effective_input is None:
            raise TypeError(
                "bulk create requires create_input or an explicit input_dataclass."
            )
        validate_input_dataclass(
            f"bulk action {bulk_action.name} input_dataclass",
            effective_input,
        )
        return

    if bulk_action.input_dataclass is None:
        msg = (
            f"Bulk action {bulk_action.name!r} requires an explicit input_dataclass "
            "for row identifiers."
        )
        raise TypeError(msg)
    validate_input_dataclass(
        f"bulk action {bulk_action.name} input_dataclass",
        bulk_action.input_dataclass,
    )

    if bulk_action.identifier_field is None or bulk_action.lookup_field is None:
        msg = f"Bulk action {bulk_action.name!r} requires identifier_field and lookup_field."
        raise TypeError(msg)

    if bulk_action.kind == "update":
        target_dataclass = bulk_action.handler_dataclass or update_input
        if target_dataclass is None:
            raise TypeError(
                "bulk update requires update_input or an explicit handler_dataclass."
            )
        validate_input_dataclass(
            f"bulk action {bulk_action.name} handler_dataclass",
            target_dataclass,
        )
        return

    if bulk_action.kind == "patch":
        target_dataclass = bulk_action.handler_dataclass or partial_update_input
        if target_dataclass is None:
            raise TypeError(
                "bulk patch requires partial_update_input or an explicit handler_dataclass."
            )
        validate_input_dataclass(
            f"bulk action {bulk_action.name} handler_dataclass",
            target_dataclass,
        )
        validate_partial_update_dataclass(target_dataclass)
        return

    if bulk_action.kind != "delete":
        raise ValueError(f"Unsupported bulk action kind {bulk_action.kind!r}.")


def validate_acl_configuration(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    custom_actions: tuple[CustomActionSpec[M], ...],
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
) -> None:
    """Validate generic ACL configuration shared by every generated endpoint."""
    validate_grouped_action_acl_runtime_requirements(acl, grouped_actions)
    if acl is None:
        return
    validate_acl_action_name("list_action", acl.list_action)
    validate_acl_action_name("retrieve_action", acl.retrieve_action)
    validate_acl_action_name("create_action", acl.create_action)
    validate_acl_action_name("update_action", acl.update_action)
    validate_acl_action_name("partial_update_action", acl.partial_update_action)
    validate_acl_action_name("destroy_action", acl.destroy_action)
    validate_list_filter_mode(acl.list_filter_mode)
    validate_callable("acl actor_resolver", acl.actor_resolver)
    validate_optional_callable(
        "acl resource_ref_from_instance",
        acl.resource_ref_from_instance,
    )
    validate_optional_callable(
        "acl resource_ref_from_create_input",
        acl.resource_ref_from_create_input,
    )
    validate_optional_callable(
        "acl resource_ref_from_update_input",
        acl.resource_ref_from_update_input,
    )
    validate_optional_callable(
        "acl resource_ref_from_patch_input",
        acl.resource_ref_from_patch_input,
    )
    validate_optional_callable("acl queryset_filter", acl.queryset_filter)
    validate_acl_runtime_requirements(acl, custom_actions)
    for custom_action in custom_actions:
        if custom_action.acl is not None:
            validate_acl_action_name(f"custom action {custom_action.name} acl", custom_action.acl)
        validate_optional_callable(
            f"custom action {custom_action.name} acl_resource_ref_resolver",
            custom_action.acl_resource_ref_resolver,
        )


def validate_acl_action_name(name: str, action: object) -> None:
    """Validate one ACL action config if it is present."""
    if action is None:
        return
    permission = getattr(action, "permission", None)
    if not isinstance(permission, str) or not permission:
        msg = f"{name} must define a non-empty permission."
        raise ValueError(msg)
    mode = getattr(action, "mode", None)
    if mode not in ("global", "scoped", "disabled"):
        msg = f"{name} mode must be 'global', 'scoped', or 'disabled'."
        raise ValueError(msg)


def validate_list_filter_mode(list_filter_mode: object) -> None:
    """Validate the factory-level ACL list filtering strategy."""
    if list_filter_mode not in ("filter", "forbid"):
        msg = "acl list_filter_mode must be 'filter' or 'forbid'."
        raise ValueError(msg)


def validate_optional_callable(name: str, value: object) -> None:
    """Validate an optional callable configuration field."""
    if value is None:
        return
    validate_callable(name, value)


def validate_acl_runtime_requirements(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO],
    custom_actions: tuple[CustomActionSpec[M], ...],
) -> None:
    """Validate resolver requirements implied by scoped ACL actions."""
    if action_requires_scoped_resolver(acl.list_action):
        if acl.resource_ref_from_instance is None and acl.queryset_filter is None:
            msg = (
                "Scoped list_action requires resource_ref_from_instance or queryset_filter."
            )
            raise TypeError(msg)
    if action_requires_scoped_resolver(acl.retrieve_action):
        require_acl_value("retrieve_action", acl.resource_ref_from_instance)
    if action_requires_scoped_resolver(acl.update_action):
        require_acl_value("update_action", acl.resource_ref_from_instance)
    if action_requires_scoped_resolver(acl.partial_update_action):
        require_acl_value("partial_update_action", acl.resource_ref_from_instance)
    if action_requires_scoped_resolver(acl.destroy_action):
        require_acl_value("destroy_action", acl.resource_ref_from_instance)
    if action_requires_scoped_resolver(acl.create_action):
        require_acl_value("create_action", acl.resource_ref_from_create_input)
    validate_custom_action_acl_runtime_requirements(acl, custom_actions)


def validate_custom_action_acl_runtime_requirements(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO],
    custom_actions: tuple[CustomActionSpec[M], ...],
) -> None:
    """Validate scoped ACL requirements for typed custom actions."""
    for custom_action in custom_actions:
        if not action_requires_scoped_resolver(custom_action.acl):
            continue
        if custom_action.detail:
            if (
                custom_action.acl_resource_ref_resolver is None
                and acl.resource_ref_from_instance is None
            ):
                msg = (
                    f"Scoped detail custom action {custom_action.name!r} requires "
                    "acl_resource_ref_resolver or factory acl.resource_ref_from_instance."
                )
                raise TypeError(msg)
            continue
        if custom_action.acl_resource_ref_resolver is None:
            msg = (
                f"Scoped collection custom action {custom_action.name!r} requires "
                "acl_resource_ref_resolver."
            )
            raise TypeError(msg)


def validate_grouped_action_methods(
    grouped_action: GroupedCollectionActionSpec[M],
) -> None:
    """Ensure grouped actions stay within the v1 GET-only contract."""
    if tuple(grouped_action.methods) != ("get",):
        msg = (
            f"Grouped action {grouped_action.name!r} only supports "
            "methods=('get',) in v1."
        )
        raise ValueError(msg)


def validate_grouped_action_source_acl(
    source_acl: GroupedCollectionSourceACL[M] | None,
) -> None:
    """Validate one grouped action source ACL block if present."""
    if source_acl is None:
        return
    if not source_acl.permission:
        msg = "grouped action source_acl.permission must be a non-empty string."
        raise ValueError(msg)
    if source_acl.mode not in ("global", "scoped", "disabled"):
        msg = "grouped action source_acl.mode must be 'global', 'scoped', or 'disabled'."
        raise ValueError(msg)
    if source_acl.list_filter_mode not in ("filter", "forbid"):
        msg = "grouped action source_acl.list_filter_mode must be 'filter' or 'forbid'."
        raise ValueError(msg)
    validate_optional_callable(
        "grouped action source_acl.resource_ref_from_instance",
        source_acl.resource_ref_from_instance,
    )
    validate_optional_callable(
        "grouped action source_acl.queryset_filter",
        source_acl.queryset_filter,
    )


def validate_grouped_action_acl_runtime_requirements(
    acl: ACLConfig[M, CreateDTO, UpdateDTO, PatchDTO] | None,
    grouped_actions: tuple[GroupedCollectionActionSpec[M], ...],
) -> None:
    """Validate grouped source ACL blocks against the factory-level ACL backend."""
    for grouped_action in grouped_actions:
        source_acl = grouped_action.source_acl
        if source_acl is None or source_acl.mode == "disabled":
            continue
        if acl is None:
            msg = (
                f"Grouped action {grouped_action.name!r} uses source_acl, "
                "but the factory does not define acl."
            )
            raise TypeError(msg)
        if (
            source_acl.mode == "scoped"
            and source_acl.resource_ref_from_instance is None
            and source_acl.queryset_filter is None
        ):
            msg = (
                f"Grouped action {grouped_action.name!r} scoped source_acl "
                "requires resource_ref_from_instance or queryset_filter."
            )
            raise TypeError(msg)


def action_requires_scoped_resolver(action: object) -> bool:
    """Return True when an ACL action config uses resource-scoped checks."""
    return getattr(action, "mode", None) == "scoped"


def require_acl_value(name: str, value: object) -> None:
    """Raise when one scoped ACL action is missing its required resolver."""
    if value is None:
        msg = f"Scoped {name} requires an ACL resolver."
        raise TypeError(msg)
