from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar, cast

BulkInputDTO = TypeVar("BulkInputDTO")
BulkTransactionMode = Literal["atomic", "best-effort"]
BulkActionKind = Literal["create", "update", "patch", "delete"]

__all__ = [
    "BulkActionKind",
    "BulkActionSpec",
    "BulkFieldErrorDTO",
    "BulkMutationResultDTO",
    "BulkRowErrorDTO",
    "BulkTransactionMode",
    "bulk_create_action",
    "bulk_delete_action",
    "bulk_patch_action",
    "bulk_update_action",
]


@dataclass(frozen=True)
class BulkFieldErrorDTO:
    """One field-level error inside a bulk row result."""

    field: str
    messages: list[str]


@dataclass(frozen=True)
class BulkRowErrorDTO:
    """One row-level validation or permission error inside a bulk operation."""

    index: int
    identifier: str | None
    errors: list[BulkFieldErrorDTO]


@dataclass
class BulkMutationResultDTO:
    """Structured result returned by generated bulk mutation endpoints."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    failed: int = 0
    rolled_back: bool = False
    succeeded_identifiers: list[str] = field(default_factory=list)
    errors: list[BulkRowErrorDTO] = field(default_factory=list)


@dataclass(frozen=True)
class BulkActionSpec(Generic[BulkInputDTO]):
    """One generated bulk mutation endpoint attached to a CRUDFactory viewset."""

    name: str
    kind: BulkActionKind
    input_dataclass: type[object] | None
    methods: tuple[str, ...]
    url_path: str | None
    url_name: str | None
    identifier_field: str | None
    lookup_field: str | None
    handler_dataclass: type[object] | None
    transaction_mode: BulkTransactionMode


def bulk_create_action(
    *,
    input_dataclass: type[BulkInputDTO] | None = None,
    methods: tuple[str, ...] = ("post",),
    name: str = "bulk_create",
    url_path: str | None = "bulk-create",
    url_name: str | None = None,
    transaction_mode: BulkTransactionMode = "atomic",
) -> BulkActionSpec[BulkInputDTO]:
    """Return a bulk create action spec.

    When `input_dataclass` is omitted, CRUDFactory uses the factory's
    `create_input` dataclass as the per-row contract.
    """
    return BulkActionSpec(
        name=name,
        kind="create",
        input_dataclass=cast(type[object] | None, input_dataclass),
        methods=normalize_bulk_action_methods(methods, expected=("post",)),
        url_path=url_path,
        url_name=url_name,
        identifier_field=None,
        lookup_field=None,
        handler_dataclass=None,
        transaction_mode=transaction_mode,
    )


def bulk_update_action(
    *,
    input_dataclass: type[BulkInputDTO],
    identifier_field: str = "id",
    lookup_field: str = "pk",
    handler_dataclass: type[object] | None = None,
    methods: tuple[str, ...] = ("put",),
    name: str = "bulk_update",
    url_path: str | None = "bulk-update",
    url_name: str | None = None,
    transaction_mode: BulkTransactionMode = "atomic",
) -> BulkActionSpec[BulkInputDTO]:
    """Return a bulk full-update action spec."""
    return BulkActionSpec(
        name=name,
        kind="update",
        input_dataclass=cast(type[object], input_dataclass),
        methods=normalize_bulk_action_methods(methods, expected=("put",)),
        url_path=url_path,
        url_name=url_name,
        identifier_field=identifier_field,
        lookup_field=lookup_field,
        handler_dataclass=handler_dataclass,
        transaction_mode=transaction_mode,
    )


def bulk_patch_action(
    *,
    input_dataclass: type[BulkInputDTO],
    identifier_field: str = "id",
    lookup_field: str = "pk",
    handler_dataclass: type[object] | None = None,
    methods: tuple[str, ...] = ("patch",),
    name: str = "bulk_patch",
    url_path: str | None = "bulk-patch",
    url_name: str | None = None,
    transaction_mode: BulkTransactionMode = "atomic",
) -> BulkActionSpec[BulkInputDTO]:
    """Return a bulk partial-update action spec."""
    return BulkActionSpec(
        name=name,
        kind="patch",
        input_dataclass=cast(type[object], input_dataclass),
        methods=normalize_bulk_action_methods(methods, expected=("patch",)),
        url_path=url_path,
        url_name=url_name,
        identifier_field=identifier_field,
        lookup_field=lookup_field,
        handler_dataclass=handler_dataclass,
        transaction_mode=transaction_mode,
    )


def bulk_delete_action(
    *,
    input_dataclass: type[BulkInputDTO],
    identifier_field: str = "id",
    lookup_field: str = "pk",
    methods: tuple[str, ...] = ("delete",),
    name: str = "bulk_delete",
    url_path: str | None = "bulk-delete",
    url_name: str | None = None,
    transaction_mode: BulkTransactionMode = "atomic",
) -> BulkActionSpec[BulkInputDTO]:
    """Return a bulk delete action spec."""
    return BulkActionSpec(
        name=name,
        kind="delete",
        input_dataclass=cast(type[object], input_dataclass),
        methods=normalize_bulk_action_methods(methods, expected=("delete",)),
        url_path=url_path,
        url_name=url_name,
        identifier_field=identifier_field,
        lookup_field=lookup_field,
        handler_dataclass=None,
        transaction_mode=transaction_mode,
    )


def normalize_bulk_action_methods(
    methods: tuple[str, ...],
    *,
    expected: tuple[str, ...],
) -> tuple[str, ...]:
    """Return lower-case methods and enforce the current v1 surface."""
    normalized_methods = tuple(method.lower() for method in methods)
    if normalized_methods != expected:
        msg = f"Bulk action only supports methods={expected!r} in v1."
        raise ValueError(msg)
    return normalized_methods
