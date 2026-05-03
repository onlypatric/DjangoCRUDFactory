from __future__ import annotations

import datetime as dt
from dataclasses import MISSING, Field, fields, is_dataclass
from decimal import Decimal
from types import UnionType
from typing import TYPE_CHECKING, Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from ._simple_writes import (
    MODEL_FIELD_METADATA_KEY,
    MODEL_READ_TRANSFORM_METADATA_KEY,
    MODEL_WRITE_TRANSFORM_METADATA_KEY,
)
from .annotations import ANNOTATION_METADATA_KEY, AnnotationDeclaration
from .filters import FILTER_METADATA_KEY, FilterDeclaration
from .field_subresources import field_subresource_payload_label
from .ordering import ORDERING_QUERY_PARAM, ORDER_METADATA_KEY
from .source_queries import SOURCE_FILTER_METADATA_KEY, SOURCE_ORDER_METADATA_KEY
from .stats import STAT_METADATA_KEY, AggregateStatDeclaration
from .validators import (
    CHOICES_METADATA_KEY,
    MAX_LENGTH_METADATA_KEY,
    MAX_VALUE_METADATA_KEY,
    MIN_LENGTH_METADATA_KEY,
    MIN_VALUE_METADATA_KEY,
    REGEX_METADATA_KEY,
)

if TYPE_CHECKING:
    from .factory import CRUDFactory


def render_factory_markdown(
    factory: CRUDFactory[Any, Any, Any, Any, Any],
    *,
    title: str | None = None,
    base_path: str = "/api",
) -> str:
    """Render a readable Markdown contract for one CRUDFactory instance."""
    response_dataclass = required_response_dataclass(factory)
    lines = [
        f"# {title or default_factory_title(factory)}",
        "",
        factory_summary_line(factory),
        "",
        "## Endpoints",
        "",
    ]
    lines.extend(endpoint_lines(factory, base_path=base_path))
    lines.append("")
    lines.append("## Query Features")
    lines.append("")
    lines.extend(query_feature_lines(factory))
    lines.append("")
    lines.append("## Request DTOs")
    lines.append("")
    lines.extend(request_section_lines(factory))
    lines.append("")
    lines.append("## Response DTO")
    lines.append("")
    lines.extend(dataclass_section_lines(response_dataclass))
    lines.append("")
    lines.append("## Field Subresource Endpoints")
    lines.append("")
    lines.extend(field_subresource_lines(factory, base_path=base_path))
    lines.append("")
    lines.append("## Error Responses")
    lines.append("")
    lines.extend(error_response_lines(factory))
    lines.append("")
    lines.append("## Custom Actions")
    lines.append("")
    lines.extend(custom_action_lines(factory))
    lines.append("")
    lines.append("## Grouped Collection Actions")
    lines.append("")
    lines.extend(grouped_action_lines(factory))
    lines.append("")
    lines.append("## Bulk Operations")
    lines.append("")
    lines.extend(bulk_action_lines(factory))
    return "\n".join(lines).strip() + "\n"


def required_response_dataclass(
    factory: CRUDFactory[Any, Any, Any, Any, Any],
) -> type[Any]:
    type_hints = get_type_hints(factory.response_mapper)
    response_dataclass = type_hints.get("return")
    if isinstance(response_dataclass, type) and is_dataclass(response_dataclass):
        return response_dataclass
    raise TypeError("CRUDFactory response mapper does not declare a dataclass return type.")


def default_factory_title(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> str:
    return f"{factory.model.__name__} Factory"


def factory_summary_line(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> str:
    mode = "read-only" if factory.is_read_only else "full CRUD"
    return (
        f"Generated `{mode}` contract for model `{factory.model.__name__}` "
        f"on route `/{factory.route.strip('/')}/` with basename `{factory.basename}`."
    )


def endpoint_lines(
    factory: CRUDFactory[Any, Any, Any, Any, Any],
    *,
    base_path: str,
) -> list[str]:
    route_path = join_route(base_path, factory.route)
    detail_path = f"{route_path}{{{factory.lookup_url_kwarg or factory.lookup_field}}}/"
    lines = [
        f"- `GET {route_path}`: list",
        f"- `GET {detail_path}`: retrieve",
    ]
    if not factory.is_read_only:
        lines.extend(
            [
                f"- `POST {route_path}`: create",
                f"- `PUT {detail_path}`: update",
                f"- `PATCH {detail_path}`: partial_update",
                f"- `DELETE {detail_path}`: destroy",
            ]
        )
    for custom_action in factory.custom_actions:
        action_path = route_path if not custom_action.detail else detail_path
        action_path = f"{action_path}{custom_action.url_path or custom_action.name}/"
        methods = ", ".join(method.upper() for method in custom_action.methods)
        lines.append(f"- `{methods} {action_path}`: {custom_action.name}")
    for grouped_action in getattr(factory, "grouped_actions", ()):
        action_path = f"{route_path}{grouped_action.url_path or grouped_action.name}/"
        methods = ", ".join(method.upper() for method in grouped_action.methods)
        lines.append(f"- `{methods} {action_path}`: grouped {grouped_action.name}")
    for bulk_action in getattr(factory, "bulk_actions", ()):
        action_path = f"{route_path}{bulk_action.url_path or bulk_action.name}/"
        methods = ", ".join(method.upper() for method in bulk_action.methods)
        lines.append(f"- `{methods} {action_path}`: bulk {bulk_action.kind}")
    for field_subresource in getattr(factory, "field_subresources", ()):
        action_path = (
            f"{detail_path}{field_subresource.url_path or field_subresource.field_name}/"
        )
        methods = ", ".join(method.upper() for method in field_subresource.methods)
        lines.append(f"- `{methods} {action_path}`: field `{field_subresource.field_name}`")
    return lines


def join_route(base_path: str, route: str) -> str:
    normalized_base = "/" + base_path.strip("/") if base_path.strip("/") else ""
    normalized_route = route.strip("/")
    return f"{normalized_base}/{normalized_route}/"


def query_feature_lines(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> list[str]:
    lines: list[str] = []
    if factory.filter_specs:
        lines.append("### Filters")
        lines.append("")
        for filter_spec in factory.filter_specs:
            lines.append(
                f"- `{filter_spec.query_param}` -> `{filter_spec.lookup}`"
            )
        lines.append("")
    if factory.order_specs:
        lines.append("### Ordering")
        lines.append("")
        lines.append(f"- Query parameter: `{ORDERING_QUERY_PARAM}`")
        for order_spec in factory.order_specs:
            lines.append(f"- `{order_spec.query_name}` -> `{order_spec.lookup}`")
        lines.append("")
    if not lines:
        return ["No filter or ordering metadata is declared."]
    return trim_trailing_blank(lines)


def request_section_lines(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> list[str]:
    sections: list[str] = []
    dto_pairs = [
        ("create", factory.create_input),
        ("update", factory.update_input),
        ("partial_update", factory.partial_update_input),
    ]
    for label, dataclass_type in dto_pairs:
        if dataclass_type is None:
            continue
        sections.append(f"### `{label}`")
        sections.append("")
        sections.extend(dataclass_section_lines(dataclass_type))
        sections.append("")
    if not sections:
        return ["This factory does not accept write input DTOs."]
    return trim_trailing_blank(sections)


def error_response_lines(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> list[str]:
    """Return a frontend-facing description of non-successful responses."""
    lines = [
        "### Frontend Parsing Rule",
        "",
        "- Successful responses follow the declared response DTOs.",
        "- Non-successful responses do not use the response DTO contract.",
        "- Frontend code should treat `4xx` and `5xx` payloads as error objects and branch on HTTP status first.",
        "",
        "### `400 Bad Request`",
        "",
        "- Used for request DTO validation errors, malformed filters or ordering, custom action input validation, and business-rule validation raised as `ValidationError`.",
        "- Field errors use a mapping of `field_name -> list[str]`.",
        "- Non-field errors usually use `detail`.",
        "",
        "```json",
        "{",
        '  "name": ["Ensure this field has at least 3 characters."]',
        "}",
        "```",
        "",
        "```json",
        "{",
        '  "detail": "Locked connectors cannot be started."',
        "}",
        "```",
        "",
        "Frontend recommendation:",
        "- Render field-keyed payloads inline on forms.",
        "- Render `detail` payloads as page-level or modal-level action errors.",
        "",
        "### `404 Not Found`",
        "",
        "- Used when the object does not exist.",
        "- Also used for ACL-protected detail endpoints and actions when `unauthorized_as_404=True`.",
        "",
        "```json",
        "{",
        '  "detail": "No Connector matches the given query."',
        "}",
        "```",
        "",
        "Frontend recommendation:",
        "- Treat `404` as a terminal state for the current resource view.",
        "- For destructive or action flows, assume the resource is unavailable or no longer visible to the actor.",
        "",
    ]
    if factory_has_forbidden_acl_mode(factory):
        lines.extend(
            [
                "### `403 Forbidden`",
                "",
                "- Used when ACL denies access with `unauthorized_as_404=False`.",
                "",
                "```json",
                "{",
                '  "detail": "You do not have permission to perform this action."',
                "}",
                "```",
                "",
                "Frontend recommendation:",
                "- Render this as an authorization failure, not a missing resource.",
                "",
            ]
        )
    lines.extend(
        [
            "### `405 Method Not Allowed`",
            "",
            "- Used when the HTTP method is not exposed by the generated factory.",
            "",
            "```json",
            "{",
            '  "detail": "Method \\"POST\\" not allowed."',
            "}",
            "```",
            "",
            "### `500 Internal Server Error`",
            "",
            "- Not part of the intended public contract.",
            "- Indicates a backend bug, bad configuration, or an uncaught runtime failure.",
            "",
            "Frontend recommendation:",
            "- Show a generic retry/failure state and log the request context for debugging.",
        ]
    )
    return lines


def custom_action_lines(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> list[str]:
    if not factory.custom_actions:
        return ["This factory does not declare custom actions."]

    lines: list[str] = []
    for custom_action in factory.custom_actions:
        lines.append(f"### `{custom_action.name}`")
        lines.append("")
        lines.append(
            f"- Scope: `{'detail' if custom_action.detail else 'collection'}`"
        )
        lines.append(
            f"- Methods: `{', '.join(method.upper() for method in custom_action.methods)}`"
        )
        if getattr(custom_action, "request_source", "body") == "query":
            lines.append("- Query DTO:")
            if custom_action.query_dataclass is not None:
                lines.extend(
                    indent_lines(dataclass_section_lines(custom_action.query_dataclass))
                )
        else:
            lines.append("- Input DTO:")
            if custom_action.input_dataclass is not None:
                lines.extend(
                    indent_lines(dataclass_section_lines(custom_action.input_dataclass))
                )
        lines.append("- Response DTO:")
        lines.extend(
            indent_lines(dataclass_section_lines(custom_action.response_dataclass))
        )
        lines.append("")
    return trim_trailing_blank(lines)


def field_subresource_lines(
    factory: CRUDFactory[Any, Any, Any, Any, Any],
    *,
    base_path: str,
) -> list[str]:
    """Describe generated single-field detail endpoints."""
    if not getattr(factory, "field_subresources", ()):
        return ["No field subresource endpoints are declared."]
    detail_path = join_route(base_path, factory.route)
    detail_path = f"{detail_path}{{{factory.lookup_url_kwarg or factory.lookup_field}}}/"
    lines: list[str] = []
    for field_subresource in factory.field_subresources:
        action_path = (
            f"{detail_path}{field_subresource.url_path or field_subresource.field_name}/"
        )
        methods = ", ".join(method.upper() for method in field_subresource.methods)
        payload_label = field_subresource_payload_label(
            model=factory.model,
            field_name=field_subresource.field_name,
        )
        lines.append(f"### `{field_subresource.field_name}`")
        lines.append("")
        lines.append(f"- Route: `{methods} {action_path}`")
        lines.append(f"- Raw payload type: `{payload_label}`")
        if "patch" in field_subresource.methods:
            lines.append(f"- PATCH mode: `{field_subresource.patch_mode}`")
        if field_subresource.read_acl is not None:
            lines.append(
                f"- Read ACL permission: `{field_subresource.read_acl.permission}`"
            )
        if field_subresource.patch_acl is not None:
            lines.append(
                f"- Patch ACL permission: `{field_subresource.patch_acl.permission}`"
            )
        lines.append("")
    return trim_trailing_blank(lines)


def grouped_action_lines(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> list[str]:
    grouped_actions = getattr(factory, "grouped_actions", ())
    if not grouped_actions:
        return ["This factory does not declare grouped collection actions."]

    lines: list[str] = []
    for grouped_action in grouped_actions:
        lines.append(f"### `{grouped_action.name}`")
        lines.append("")
        lines.append("- Scope: `collection`")
        lines.append(
            f"- Methods: `{', '.join(method.upper() for method in grouped_action.methods)}`"
        )
        if grouped_action.source_acl is not None:
            lines.append(
                f"- Source ACL: `{grouped_action.source_acl.mode}` on permission "
                f"`{grouped_action.source_acl.permission}`"
            )
        lines.append("- Query DTO:")
        lines.extend(indent_lines(dataclass_section_lines(grouped_action.query_dataclass)))
        lines.append("- Response DTO:")
        lines.extend(
            indent_lines(dataclass_section_lines(grouped_action.response_dataclass))
        )
        lines.append("")
    return trim_trailing_blank(lines)


def bulk_action_lines(factory: CRUDFactory[Any, Any, Any, Any, Any]) -> list[str]:
    """Describe generated bulk mutation endpoints."""
    bulk_actions = getattr(factory, "bulk_actions", ())
    if not bulk_actions:
        return ["This factory does not declare bulk mutation endpoints."]

    lines: list[str] = []
    for bulk_action in bulk_actions:
        lines.append(f"### `{bulk_action.name}`")
        lines.append("")
        lines.append(f"- Kind: `{bulk_action.kind}`")
        lines.append(
            f"- Methods: `{', '.join(method.upper() for method in bulk_action.methods)}`"
        )
        lines.append(f"- Transaction mode: `{bulk_action.transaction_mode}`")
        if bulk_action.identifier_field is not None:
            lines.append(f"- Identifier field: `{bulk_action.identifier_field}`")
        if bulk_action.lookup_field is not None:
            lines.append(f"- Lookup field: `{bulk_action.lookup_field}`")
        lines.append("- Row DTO:")
        input_dataclass = bulk_action.input_dataclass
        if input_dataclass is not None:
            lines.extend(indent_lines(dataclass_section_lines(input_dataclass)))
        else:
            lines.append("  - Uses the factory `create_input` contract.")
        lines.append("- Result DTO:")
        from .bulk_actions import BulkMutationResultDTO

        lines.extend(indent_lines(dataclass_section_lines(BulkMutationResultDTO)))
        lines.append("")
    return trim_trailing_blank(lines)


def dataclass_section_lines(dataclass_type: type[Any]) -> list[str]:
    type_hints = get_type_hints(dataclass_type)
    lines = [f"### `{dataclass_type.__name__}`", ""]
    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        lines.append(field_signature_line(dataclass_field, field_type))
        metadata_lines = field_metadata_lines(dataclass_field)
        if metadata_lines:
            lines.extend(indent_lines(metadata_lines))
    nested_types = nested_dataclass_types(dataclass_type)
    for nested_type in nested_types:
        lines.append("")
        lines.extend(dataclass_section_lines(nested_type))
    return lines


def field_signature_line(dataclass_field: Field[Any], field_type: object) -> str:
    required_label = "required" if is_required_field(dataclass_field) else "optional"
    return (
        f"- `{dataclass_field.name}: {format_type_annotation(field_type)}`"
        f" ({required_label})"
    )


def field_metadata_lines(dataclass_field: Field[Any]) -> list[str]:
    lines: list[str] = []
    metadata = dataclass_field.metadata
    if MODEL_FIELD_METADATA_KEY in metadata:
        lines.append(f"Source field: `{metadata[MODEL_FIELD_METADATA_KEY]}`")
    if MODEL_READ_TRANSFORM_METADATA_KEY in metadata:
        lines.append("Read transform: yes")
    if MODEL_WRITE_TRANSFORM_METADATA_KEY in metadata:
        lines.append("Write transform: yes")
    if FILTER_METADATA_KEY in metadata:
        declaration = metadata[FILTER_METADATA_KEY]
        if isinstance(declaration, FilterDeclaration):
            lookup = declaration.lookup or dataclass_field.name
            lines.append(
                f"Filterable: `{lookup}` with lookups `{', '.join(declaration.lookups)}`"
            )
    if SOURCE_FILTER_METADATA_KEY in metadata:
        declaration = metadata[SOURCE_FILTER_METADATA_KEY]
        if isinstance(declaration, FilterDeclaration):
            lookup = declaration.lookup or dataclass_field.name
            lines.append(
                f"Source filterable: `{lookup}` with lookups `{', '.join(declaration.lookups)}`"
            )
    if ORDER_METADATA_KEY in metadata:
        raw_order = metadata[ORDER_METADATA_KEY]
        if raw_order is True:
            lines.append(f"Orderable: `{dataclass_field.name}`")
        elif isinstance(raw_order, str):
            lines.append(f"Orderable: `{raw_order}`")
    if SOURCE_ORDER_METADATA_KEY in metadata:
        raw_order = metadata[SOURCE_ORDER_METADATA_KEY]
        if raw_order is True:
            lines.append(f"Source orderable: `{dataclass_field.name}`")
        elif isinstance(raw_order, str):
            lines.append(f"Source orderable: `{raw_order}`")
    if STAT_METADATA_KEY in metadata:
        declaration = metadata[STAT_METADATA_KEY]
        if isinstance(declaration, AggregateStatDeclaration):
            stat_bits = [f"{declaration.aggregate_name} `{declaration.lookup}`"]
            if declaration.filter is not None:
                stat_bits.append(f"filter `{declaration.filter}`")
            if declaration.distinct:
                stat_bits.append("distinct")
            lines.append("Stat: " + ", ".join(stat_bits))
    if ANNOTATION_METADATA_KEY in metadata:
        declaration = metadata[ANNOTATION_METADATA_KEY]
        if isinstance(declaration, AnnotationDeclaration):
            annotation_bits = ["declarative queryset annotation"]
            if declaration.alias is not None:
                annotation_bits.append(f"logical alias `{declaration.alias}`")
            lines.append("Annotation: " + ", ".join(annotation_bits))
    if REGEX_METADATA_KEY in metadata:
        lines.append(f"Regex: `{metadata[REGEX_METADATA_KEY]}`")
    if MIN_VALUE_METADATA_KEY in metadata or MAX_VALUE_METADATA_KEY in metadata:
        range_bits: list[str] = []
        if MIN_VALUE_METADATA_KEY in metadata:
            range_bits.append(f"min `{metadata[MIN_VALUE_METADATA_KEY]}`")
        if MAX_VALUE_METADATA_KEY in metadata:
            range_bits.append(f"max `{metadata[MAX_VALUE_METADATA_KEY]}`")
        lines.append("Range: " + ", ".join(range_bits))
    if MIN_LENGTH_METADATA_KEY in metadata or MAX_LENGTH_METADATA_KEY in metadata:
        length_bits: list[str] = []
        if MIN_LENGTH_METADATA_KEY in metadata:
            length_bits.append(f"min `{metadata[MIN_LENGTH_METADATA_KEY]}`")
        if MAX_LENGTH_METADATA_KEY in metadata:
            length_bits.append(f"max `{metadata[MAX_LENGTH_METADATA_KEY]}`")
        lines.append("Length: " + ", ".join(length_bits))
    if CHOICES_METADATA_KEY in metadata:
        choices = metadata[CHOICES_METADATA_KEY]
        if isinstance(choices, tuple):
            lines.append(
                "Choices: " + ", ".join(f"`{choice}`" for choice in choices)
            )
    return lines


def nested_dataclass_types(dataclass_type: type[Any]) -> list[type[Any]]:
    nested: list[type[Any]] = []
    type_hints = get_type_hints(dataclass_type)
    for dataclass_field in fields(dataclass_type):
        field_type = type_hints.get(dataclass_field.name, dataclass_field.type)
        nested_type = unwrap_dataclass_type(field_type)
        if nested_type is not None and nested_type not in nested:
            nested.append(nested_type)
            continue
        list_child_type = unwrap_list_dataclass_type(field_type)
        if list_child_type is not None and list_child_type not in nested:
            nested.append(list_child_type)
    return nested


def unwrap_dataclass_type(field_type: object) -> type[Any] | None:
    unwrapped = unwrap_optional_type(field_type)
    if isinstance(unwrapped, type) and is_dataclass(unwrapped):
        return unwrapped
    return None


def unwrap_list_dataclass_type(field_type: object) -> type[Any] | None:
    unwrapped = unwrap_optional_type(field_type)
    if get_origin(unwrapped) is not list:
        return None
    args = get_args(unwrapped)
    if len(args) != 1:
        return None
    child_type = unwrap_optional_type(args[0])
    if isinstance(child_type, type) and is_dataclass(child_type):
        return child_type
    return None


def unwrap_optional_type(field_type: object) -> object:
    origin = get_origin(field_type)
    if origin not in (UnionType, None) and origin is not None:
        return field_type
    args = get_args(field_type)
    if not args:
        return field_type
    non_none_args = [argument for argument in args if argument is not type(None)]
    if len(non_none_args) == 1 and len(non_none_args) != len(args):
        return non_none_args[0]
    return field_type


def format_type_annotation(field_type: object) -> str:
    if field_type is str:
        return "str"
    if field_type is int:
        return "int"
    if field_type is float:
        return "float"
    if field_type is bool:
        return "bool"
    if field_type is dt.date:
        return "date"
    if field_type is dt.datetime:
        return "datetime"
    if field_type is Decimal:
        return "Decimal"
    if field_type is UUID:
        return "UUID"
    origin = get_origin(field_type)
    if origin is list:
        args = get_args(field_type)
        child = args[0] if args else Any
        return f"list[{format_type_annotation(child)}]"
    if origin in (UnionType, Union):
        return " | ".join(format_type_annotation(argument) for argument in get_args(field_type))
    if isinstance(field_type, type):
        return field_type.__name__
    return repr(field_type)


def is_required_field(dataclass_field: Field[Any]) -> bool:
    return dataclass_field.default is MISSING and dataclass_field.default_factory is MISSING


def indent_lines(lines: list[str]) -> list[str]:
    return [f"  {line}" if line else "" for line in lines]


def trim_trailing_blank(lines: list[str]) -> list[str]:
    while lines and not lines[-1]:
        lines.pop()
    return lines


def factory_has_forbidden_acl_mode(
    factory: CRUDFactory[Any, Any, Any, Any, Any],
) -> bool:
    """Return True when any configured ACL path can return a 403 response."""
    acl = factory.acl
    if acl is not None:
        for action_name in (
            "list_action",
            "retrieve_action",
            "create_action",
            "update_action",
            "partial_update_action",
            "destroy_action",
        ):
            action = getattr(acl, action_name)
            if action is not None and not action.unauthorized_as_404:
                return True
    for custom_action in factory.custom_actions:
        action_acl = custom_action.acl
        if action_acl is not None and not action_acl.unauthorized_as_404:
            return True
    return False
