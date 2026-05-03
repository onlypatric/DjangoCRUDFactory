from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import dataclass, field, fields as dataclass_fields
from collections.abc import Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import ANY, MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls.resolvers import URLPattern, URLResolver

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "rest_framework",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            },
        },
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
        ROOT_URLCONF=__name__,
        SECRET_KEY="crudfactory-tests",
        REST_FRAMEWORK={"UNAUTHENTICATED_USER": None},
    )

import django
from django.db import connection, models
from django.db.models import Case, Exists, OuterRef, Q, Subquery, Value, When
from rest_framework.permissions import BasePermission
from rest_framework.routers import SimpleRouter
from rest_framework import serializers
from rest_framework.test import APIRequestFactory
from rest_framework.viewsets import ModelViewSet

django.setup()

from crudfactory import (
    ACLActionConfig,
    ACLBackend,
    ACLConfig,
    CRUDFactory,
    GroupedCollectionSourceACL,
    QueryPlan,
    avg_stat,
    annotated_field,
    bulk_create_action,
    bulk_delete_action,
    bulk_patch_action,
    collection_action,
    choices,
    compose_meta,
    auto_query_plan,
    derive_query_plan,
    grouped_collection_action,
    count_stat,
    enum_summary,
    field_subresource,
    filterable,
    global_read_acl,
    global_read_write_acl,
    length,
    latest_related_value,
    max_stat,
    min_stat,
    model_field,
    nested_relation,
    orderable,
    parent_scope,
    query_exclude,
    query_list,
    query_ordering,
    query_range,
    query_search,
    range_,
    regex,
    related_list,
    scoped_read_acl,
    scoped_read_write_acl,
    soft_delete_lifecycle,
    source_filterable,
    source_orderable,
    sum_stat,
)
from crudfactory.acl_tables import ensure_acl_tables_exist
from crudfactory.config import get_crudfactory_settings
from crudfactory.dataclass_serializers import build_serializer_from_dataclass


class Widget(models.Model):
    name = models.CharField(max_length=50)
    count = models.IntegerField(default=0)
    secret = models.CharField(max_length=50, default="")
    metadata = models.JSONField(default=dict, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "tests"

    if TYPE_CHECKING:
        id: int


class NestedWidget(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        app_label = "tests"

    if TYPE_CHECKING:
        id: int
        children: models.Manager[NestedWidgetChild]


class NestedWidgetChild(models.Model):
    widget = models.ForeignKey(
        NestedWidget,
        on_delete=models.CASCADE,
        related_name="children",
    )
    name = models.CharField(max_length=50)
    status = models.CharField(max_length=20)

    class Meta:
        app_label = "tests"

    if TYPE_CHECKING:
        id: int
        widget_id: int


class WidgetReading(models.Model):
    widget = models.ForeignKey(
        Widget,
        on_delete=models.CASCADE,
        related_name="readings",
    )
    value = models.IntegerField(default=0)
    label = models.CharField(max_length=50, default="")

    class Meta:
        app_label = "tests"

    if TYPE_CHECKING:
        id: int


class CrudFactorySettingsTests(SimpleTestCase):
    @override_settings(
        CRUDFACTORY={
            "ACL_ENABLED": False,
            "ACL_AUTO_CREATE_TABLES": True,
        }
    )
    def test_nested_crudfactory_settings_are_read(self) -> None:
        configured = get_crudfactory_settings()

        self.assertFalse(configured.acl_enabled)
        self.assertTrue(configured.acl_auto_create_tables)

    @override_settings(
        CRUDFACTORY_ACL_ENABLED=False,
        CRUDFACTORY_ACL_AUTO_CREATE_TABLES=True,
    )
    def test_legacy_top_level_settings_are_read(self) -> None:
        configured = get_crudfactory_settings()

        self.assertFalse(configured.acl_enabled)
        self.assertTrue(configured.acl_auto_create_tables)


class ACLTableCreationTests(SimpleTestCase):
    @patch("crudfactory.acl_tables.connection")
    def test_ensure_acl_tables_creates_only_missing_tables(
        self,
        mocked_connection: MagicMock,
    ) -> None:
        mocked_connection.introspection.table_names.return_value = [
            "app_acl_permission",
            "app_acl_group",
        ]
        schema_editor = MagicMock()
        mocked_connection.schema_editor.return_value.__enter__.return_value = schema_editor

        ensure_acl_tables_exist()

        created_model_tables = [
            call.args[0]._meta.db_table
            for call in schema_editor.create_model.call_args_list
        ]

        self.assertNotIn("app_acl_permission", created_model_tables)
        self.assertNotIn("app_acl_group", created_model_tables)
        self.assertIn("app_acl_group_member", created_model_tables)
        self.assertIn("app_acl_resource_node", created_model_tables)
        self.assertIn("app_acl_resource_closure", created_model_tables)
        self.assertIn("app_acl_grant", created_model_tables)
        self.assertIn("app_acl_audit_log", created_model_tables)


class ACLPresetTests(SimpleTestCase):
    def test_scoped_read_acl_enables_only_read_actions(self) -> None:
        acl = scoped_read_acl(
            backend=FakeACLBackend(),
            permission="app.widgets.read",
            resource_ref_from_instance=lambda widget: cast(Widget, widget).name,
        )

        self.assertEqual(acl.list_action, ACLActionConfig(permission="app.widgets.read"))
        self.assertEqual(acl.retrieve_action, ACLActionConfig(permission="app.widgets.read"))
        self.assertIsNone(acl.create_action)
        self.assertIsNone(acl.update_action)
        self.assertIsNone(acl.partial_update_action)
        self.assertIsNone(acl.destroy_action)
        self.assertIsNotNone(acl.resource_ref_from_instance)

    def test_scoped_read_write_acl_enables_full_crud_actions(self) -> None:
        acl = scoped_read_write_acl(
            backend=FakeACLBackend(),
            read_permission="app.widgets.read",
            create_permission="app.widgets.create",
            update_permission="app.widgets.update",
            delete_permission="app.widgets.delete",
            resource_ref_from_instance=lambda widget: cast(Widget, widget).name,
            resource_ref_from_create_input=lambda dto: cast(WidgetCreateDTO, dto).name,
            resource_ref_from_update_input=lambda widget, dto: cast(
                WidgetUpdateDTO, dto
            ).name,
            resource_ref_from_patch_input=lambda widget, dto: (
                cast(WidgetPatchDTO, dto).name or cast(Widget, widget).name
            ),
        )

        self.assertEqual(acl.list_action, ACLActionConfig(permission="app.widgets.read"))
        self.assertEqual(acl.retrieve_action, ACLActionConfig(permission="app.widgets.read"))
        self.assertEqual(
            acl.create_action,
            ACLActionConfig(permission="app.widgets.create"),
        )
        self.assertEqual(
            acl.update_action,
            ACLActionConfig(permission="app.widgets.update"),
        )
        self.assertEqual(
            acl.partial_update_action,
            ACLActionConfig(permission="app.widgets.update"),
        )
        self.assertEqual(
            acl.destroy_action,
            ACLActionConfig(permission="app.widgets.delete"),
        )
        self.assertIsNotNone(acl.resource_ref_from_create_input)
        self.assertIsNotNone(acl.resource_ref_from_update_input)
        self.assertIsNotNone(acl.resource_ref_from_patch_input)

    def test_global_read_acl_sets_global_mode(self) -> None:
        acl = global_read_acl(
            backend=FakeACLBackend(),
            permission="app.widgets.read",
        )

        self.assertEqual(
            acl.list_action,
            ACLActionConfig(permission="app.widgets.read", mode="global"),
        )
        self.assertEqual(
            acl.retrieve_action,
            ACLActionConfig(permission="app.widgets.read", mode="global"),
        )
        self.assertIsNone(acl.resource_ref_from_instance)

    def test_global_read_write_acl_enables_full_crud_actions(self) -> None:
        acl = global_read_write_acl(
            backend=FakeACLBackend(),
            read_permission="app.widgets.read",
            create_permission="app.widgets.create",
            update_permission="app.widgets.update",
            delete_permission="app.widgets.delete",
        )

        self.assertEqual(
            acl.create_action,
            ACLActionConfig(permission="app.widgets.create", mode="global"),
        )
        self.assertEqual(
            acl.update_action,
            ACLActionConfig(permission="app.widgets.update", mode="global"),
        )
        self.assertEqual(
            acl.partial_update_action,
            ACLActionConfig(permission="app.widgets.update", mode="global"),
        )
        self.assertEqual(
            acl.destroy_action,
            ACLActionConfig(permission="app.widgets.delete", mode="global"),
        )


class MetadataCompositionTests(SimpleTestCase):
    def test_compose_meta_merges_distinct_fragments(self) -> None:
        metadata = compose_meta(
            model_field("name"),
            filterable(lookups=("exact", "icontains")),
            orderable(),
        )

        self.assertIn("crudfactory_model_field", metadata)
        self.assertIn("crudfactory_filter", metadata)
        self.assertIn("crudfactory_order", metadata)

    def test_compose_meta_rejects_duplicate_metadata_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate metadata key"):
            compose_meta(filterable(), filterable("name"))

    def test_compose_meta_rejects_non_mapping_fragments(self) -> None:
        with self.assertRaisesRegex(TypeError, "expects metadata mappings"):
            compose_meta(cast(Any, "not-a-mapping"))


@dataclass
class WidgetCreateDTO:
    name: str = field(metadata={**regex(r"^[a-z]+$"), **length(min=2, max=12)})
    count: int = field(metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])})


@dataclass
class WidgetUpdateDTO:
    name: str = field(metadata={**regex(r"^[a-z]+$"), **length(min=2, max=12)})
    count: int = field(metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])})


@dataclass
class WidgetPatchDTO:
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[a-z]+$"), **length(min=2, max=12)},
    )
    count: int | None = field(
        default=None,
        metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])},
    )


@dataclass
class SimpleWidgetCreateDTO:
    public_name: str = field(
        metadata={
            **model_field("name"),
            **filterable("name", lookups=("exact", "icontains")),
            **orderable("name"),
            **regex(r"^[a-z]+$"),
            **length(min=2, max=12),
        }
    )
    count: int = field(metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])})


@dataclass
class SimpleWidgetUpdateDTO:
    public_name: str = field(
        metadata={
            **model_field("name"),
            **filterable("name", lookups=("exact", "icontains")),
            **orderable("name"),
            **regex(r"^[a-z]+$"),
            **length(min=2, max=12),
        }
    )
    count: int = field(metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])})


@dataclass
class SimpleWidgetPatchDTO:
    public_name: str | None = field(
        default=None,
        metadata={
            **model_field("name"),
            **regex(r"^[a-z]+$"),
            **length(min=2, max=12),
        },
    )
    count: int | None = field(
        default=None,
        metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])},
    )


@dataclass
class NestedChildCreateDTO:
    name: str
    status: str


@dataclass
class NestedChildUpdateDTO:
    id: int | None = None
    name: str = ""
    status: str = ""


@dataclass
class NestedChildPatchDTO:
    id: int | None = None
    name: str | None = None
    status: str | None = None


@dataclass
class NestedWidgetCreateDTO:
    name: str
    children: list[NestedChildCreateDTO] = field(default_factory=list)


@dataclass
class NestedWidgetUpdateDTO:
    name: str
    children: list[NestedChildUpdateDTO]


@dataclass
class NestedWidgetPatchDTO:
    name: str | None = None
    children: list[NestedChildPatchDTO] | None = None


@dataclass
class NestedChildResponseDTO:
    id: int = field(metadata=model_field("pk"))
    name: str
    status: str


@dataclass
class NestedWidgetResponseDTO:
    id: int = field(metadata=model_field("pk"))
    name: str
    children: list[NestedChildResponseDTO] = field(
        default_factory=list,
        metadata=model_field("children"),
    )


@dataclass
class NestedWidgetChildRelatedResponseDTO:
    id: int = field(metadata=model_field("pk"))
    widget_name: str = field(metadata=model_field("widget__name"))
    status: str


@dataclass
class NestedWidgetChildCreateDTO:
    widget_id: int = field(metadata={**model_field("widget_id"), **range_(min=1, max=999999)})
    name: str
    status: str


@dataclass
class NestedWidgetChildUpdateDTO:
    widget_id: int = field(metadata={**model_field("widget_id"), **range_(min=1, max=999999)})
    name: str
    status: str


@dataclass
class NestedWidgetChildPatchDTO:
    widget_id: int | None = field(
        default=None,
        metadata={**model_field("widget_id"), **range_(min=1, max=999999)},
    )
    name: str | None = None
    status: str | None = None


@dataclass
class NestedWidgetChildResponseDTO:
    id: int = field(metadata=model_field("pk"))
    widget_id: int
    name: str
    status: str


@dataclass
class FilteredNestedWidgetResponseDTO:
    id: int = field(metadata=model_field("pk"))
    name: str
    children: list[NestedChildResponseDTO] = field(
        default_factory=list,
        metadata=related_list(
            "children",
            queryset=NestedWidgetChild.objects.filter(status="online").order_by("id"),
        ),
    )


@dataclass
class InvalidMappedFieldDTO:
    public_name: str = field(metadata=model_field("missing_model_field"))


@dataclass
class DuplicateMappedFieldDTO:
    first_name: str = field(metadata=model_field("name"))
    second_name: str = field(metadata=model_field("name"))


def count_to_label(value: object) -> str:
    return f"count:{value}"


def label_to_count(value: object) -> int:
    if not isinstance(value, str):
        msg = "count label must be a string."
        raise TypeError(msg)
    return int(value.removeprefix("count:"))


@dataclass
class TransformWidgetCreateDTO:
    name: str
    count_label: str = field(
        metadata=model_field(
            "count",
            read_transform=count_to_label,
            write_transform=label_to_count,
        )
    )


@dataclass
class TransformWidgetUpdateDTO:
    name: str
    count_label: str = field(
        metadata=model_field(
            "count",
            read_transform=count_to_label,
            write_transform=label_to_count,
        )
    )


@dataclass
class TransformWidgetPatchDTO:
    name: str | None = None
    count_label: str | None = field(
        default=None,
        metadata=model_field(
            "count",
            read_transform=count_to_label,
            write_transform=label_to_count,
        ),
    )


@dataclass
class InvalidWidgetPatchDTO:
    name: str


@dataclass
class InvalidRegexDTO:
    count: int = field(metadata=regex(r"^\d+$"))


@dataclass
class InvalidRangeDTO:
    name: str = field(metadata=range_(min=1))


@dataclass
class InvalidLengthDTO:
    count: int = field(metadata=length(min=1))


@dataclass
class AdvancedValidationDTO:
    ratio: float = field(metadata=range_(min=0.1, max=0.9))
    starts_on: dt.date = field(metadata=range_(min=dt.date(2026, 1, 1)))
    tags: list[str] = field(metadata=length(min=1, max=2))


@dataclass
class WidgetResponseDTO:
    id: int
    name: str = field(
        metadata={
            **filterable(lookups=("exact", "icontains", "in")),
            **orderable(),
        }
    )
    count: int = field(
        metadata={
            **filterable(lookups=("gte", "lte")),
            **orderable(),
        }
    )
    label: str


@dataclass
class WidgetAvailabilityStatsDTO:
    online: int = count_stat("id", filter=Q(count__gte=5))
    offline: int = count_stat("id", filter=Q(count__lt=5))
    faulted: int = count_stat("id", filter=Q(secret="faulted"))


class WidgetReadingLabelEnum(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    FAULTED = "faulted"


@enum_summary(
    enum=WidgetReadingLabelEnum,
    lookup="",
    value_field="secret",
)
@dataclass
class WidgetEnumAvailabilityStatsDTO:
    pass


@dataclass
class WidgetScoreStatsDTO:
    total: int = sum_stat("count", default=0)
    average: float | None = avg_stat("count")
    minimum: int | None = min_stat("count")
    maximum: int | None = max_stat("count")


@dataclass
class WidgetStatsResponseDTO:
    id: int
    name: str
    availability: WidgetAvailabilityStatsDTO = field(
        default_factory=WidgetAvailabilityStatsDTO
    )
    scores: WidgetScoreStatsDTO = field(default_factory=WidgetScoreStatsDTO)


@dataclass
class WidgetEnumStatsResponseDTO:
    id: int
    name: str
    availability: WidgetEnumAvailabilityStatsDTO = field(
        default_factory=WidgetEnumAvailabilityStatsDTO
    )


@dataclass
class WidgetAnnotatedResponseDTO:
    id: int
    name: str
    mirrored_count: int = field(
        metadata=annotated_field(
            annotation=Subquery(
                Widget.objects.filter(pk=OuterRef("pk")).values("count")[:1]
            ),
            default=0,
        )
    )
    state_label: str = field(
        metadata=annotated_field(
            annotation=Case(
                When(count__gte=5, then=Value("busy")),
                default=Value("idle"),
            ),
            default="idle",
        )
    )
    has_high_count: bool = field(
        metadata=annotated_field(
            annotation=Exists(Widget.objects.filter(pk=OuterRef("pk"), count__gte=8)),
            default=False,
        )
    )


@dataclass
class WidgetLatestReadingDTO:
    value: int | None = field(
        default=None,
        metadata=latest_related_value(
            model=WidgetReading,
            fk_field="widget",
            value_field="value",
            order_by="-id",
            default=None,
        ),
    )
    label: str | None = field(
        default=None,
        metadata=latest_related_value(
            model=WidgetReading,
            fk_field="widget",
            value_field="label",
            order_by="-id",
            default=None,
        ),
    )


@dataclass
class WidgetLatestResponseDTO:
    id: int
    name: str
    latest_value: int | None = field(
        default=None,
        metadata=latest_related_value(
            model=WidgetReading,
            fk_field="widget",
            value_field="value",
            order_by="-id",
            default=None,
        ),
    )
    latest_reading: WidgetLatestReadingDTO = field(
        default_factory=WidgetLatestReadingDTO
    )


@dataclass
class InvalidWidgetLatestResponseDTO:
    id: int
    latest_value: int | None = field(
        default=None,
        metadata=latest_related_value(
            value_field="value",
            order_by="-id",
            default=None,
        ),
    )


@dataclass
class InvalidWidgetAnnotationResponseDTO:
    id: int
    bad_value: int = field(
        metadata=annotated_field(
            annotation=cast(Any, "not-a-django-expression"),
            default=0,
        )
    )


@dataclass
class InvalidNestedResponseDTO:
    values_by_name: dict[str, int]


@dataclass
class InvalidNestedWrapperResponseDTO:
    nested: InvalidNestedResponseDTO


@dataclass
class WidgetGroupQueryDTO:
    name: str | None = field(
        default=None,
        metadata=source_filterable(lookups=("exact", "icontains")),
    )
    count: int | None = field(
        default=None,
        metadata=source_filterable(lookups=("gte", "lte")),
    )
    label: str | None = field(
        default=None,
        metadata=source_orderable("name"),
    )


@dataclass
class WidgetGroupItemDTO:
    id: int
    name: str


@dataclass
class WidgetGroupBucketDTO:
    label: str
    items: list[WidgetGroupItemDTO]


@dataclass
class WidgetGroupResponseDTO:
    buckets: list[WidgetGroupBucketDTO]


@dataclass
class WidgetQueryActionDTO:
    name: str | None = None
    min_count: int | None = None


@dataclass
class WidgetQueryActionItemDTO:
    id: int
    name: str


@dataclass
class WidgetQueryActionResponseDTO:
    total: int
    items: list[WidgetQueryActionItemDTO]


@dataclass
class WidgetBodyCollectionActionDTO:
    name: str


@dataclass
class WidgetListQueryDTO:
    names: list[str] | None = field(default=None, metadata=query_list("name"))
    min_count: int | None = field(default=None, metadata=query_range("count", op="gte"))
    max_count: int | None = field(default=None, metadata=query_range("count", op="lte"))
    search: str | None = field(default=None, metadata=query_search("name", "secret"))
    exclude_name: str | None = field(
        default=None,
        metadata=query_exclude("name", op="icontains"),
    )
    sort: str | None = field(default=None, metadata=query_ordering("name", "count"))


@dataclass
class WidgetBulkPatchDTO:
    id: int
    name: str | None = field(
        default=None,
        metadata={**regex(r"^[a-z]+$"), **length(min=2, max=12)},
    )
    count: int | None = field(
        default=None,
        metadata={**range_(min=0, max=10), **choices([1, 3, 8, 9])},
    )


@dataclass
class WidgetBulkDeleteDTO:
    id: int = field(metadata=range_(min=1, max=9999))


class CustomPermission(BasePermission):
    pass


class FakeACLBackend(ACLBackend):
    def has_permission(self, actor: object, permission: str) -> bool:
        return True

    def has_permission_on_resource(
        self,
        actor: object,
        permission: str,
        resource_ref: object,
    ) -> bool:
        return True


class SelectiveACLBackend(ACLBackend):
    def has_permission(self, actor: object, permission: str) -> bool:
        _ = actor, permission
        return True

    def has_permission_on_resource(
        self,
        actor: object,
        permission: str,
        resource_ref: object,
    ) -> bool:
        _ = actor, permission
        return resource_ref == "allowed"


def widget_to_response(widget: Widget) -> WidgetResponseDTO:
    return WidgetResponseDTO(
        id=cast(int, widget.pk),
        name=widget.name,
        count=widget.count,
        label=f"{widget.name}:{widget.count}",
    )


def widget_to_stats_response(widget: Widget) -> WidgetStatsResponseDTO:
    return WidgetStatsResponseDTO(
        id=cast(int, widget.pk),
        name=widget.name,
    )


def widget_to_enum_stats_response(widget: Widget) -> WidgetEnumStatsResponseDTO:
    return WidgetEnumStatsResponseDTO(
        id=cast(int, widget.pk),
        name=widget.name,
    )


def widget_to_unannotated_response(widget: Widget):
    return widget_to_response(widget)


def widget_to_non_dataclass_response(widget: Widget) -> dict[str, object]:
    return {"id": widget.pk}


def widget_to_invalid_nested_response(widget: Widget) -> InvalidNestedWrapperResponseDTO:
    return InvalidNestedWrapperResponseDTO(
        nested=InvalidNestedResponseDTO(values_by_name={widget.name: widget.count})
    )


def widget_to_wrong_runtime_response(widget: Widget) -> WidgetResponseDTO:
    return cast(WidgetResponseDTO, {"id": widget.pk})


def pattern_names(patterns: Sequence[URLPattern | URLResolver]) -> set[str]:
    return {
        pattern.name
        for pattern in patterns
        if isinstance(pattern, URLPattern) and pattern.name is not None
    }


def widget_group_response(
    widgets: models.QuerySet[Widget] | Sequence[Widget],
    _query: WidgetGroupQueryDTO,
) -> WidgetGroupResponseDTO:
    return WidgetGroupResponseDTO(
        buckets=[
            WidgetGroupBucketDTO(
                label="all",
                items=[
                    WidgetGroupItemDTO(id=cast(int, widget.pk), name=widget.name)
                    for widget in widgets
                ],
            )
        ]
    )


def widget_query_action_response(
    widgets: models.QuerySet[Widget],
    query: WidgetQueryActionDTO,
) -> WidgetQueryActionResponseDTO:
    filtered = widgets
    if query.name is not None:
        filtered = filtered.filter(name__icontains=query.name)
    if query.min_count is not None:
        filtered = filtered.filter(count__gte=query.min_count)
    items = list(filtered.order_by("id"))
    return WidgetQueryActionResponseDTO(
        total=len(items),
        items=[
            WidgetQueryActionItemDTO(id=cast(int, widget.pk), name=widget.name)
            for widget in items
        ],
    )


def widget_body_collection_action_response(
    widgets: models.QuerySet[Widget],
    dto: WidgetBodyCollectionActionDTO,
) -> WidgetQueryActionResponseDTO:
    _ = widgets
    return WidgetQueryActionResponseDTO(
        total=1,
        items=[WidgetQueryActionItemDTO(id=0, name=dto.name)],
    )


class CRUDFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(Widget)
            schema_editor.create_model(WidgetReading)
            schema_editor.create_model(NestedWidget)
            schema_editor.create_model(NestedWidgetChild)

    @classmethod
    def tearDownClass(cls) -> None:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(NestedWidgetChild)
            schema_editor.delete_model(NestedWidget)
            schema_editor.delete_model(WidgetReading)
            schema_editor.delete_model(Widget)
        super().tearDownClass()

    def setUp(self) -> None:
        WidgetReading.objects.all().delete()
        Widget.objects.all().delete()
        NestedWidgetChild.objects.all().delete()
        NestedWidget.objects.all().delete()
        self.request_factory = APIRequestFactory()
        self.created_payloads: list[WidgetCreateDTO] = []
        self.updated_payloads: list[WidgetUpdateDTO] = []
        self.patched_payloads: list[WidgetPatchDTO] = []

    def build_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_mapper": widget_to_response,
            "create_input": WidgetCreateDTO,
            "update_input": WidgetUpdateDTO,
            "partial_update_input": WidgetPatchDTO,
            "create_handler": self.create_widget,
            "update_handler": self.update_widget,
            "partial_update_handler": self.patch_widget,
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_stats_factory(self, **overrides: object) -> CRUDFactory:
        return self.build_factory(
            response_mapper=widget_to_stats_response,
            queryset=Widget.objects.order_by("id"),
            **overrides,
        )

    def build_enum_stats_factory(self, **overrides: object) -> CRUDFactory:
        return self.build_factory(
            response_mapper=widget_to_enum_stats_response,
            queryset=Widget.objects.order_by("id"),
            **overrides,
        )

    def build_annotation_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_dataclass": WidgetAnnotatedResponseDTO,
            "queryset": Widget.objects.order_by("id"),
            "read_only": True,
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_latest_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_dataclass": WidgetLatestResponseDTO,
            "queryset": Widget.objects.order_by("id"),
            "read_only": True,
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_soft_delete_factory(self, **overrides: object) -> CRUDFactory:
        config: dict[str, object] = {
            "lifecycle": soft_delete_lifecycle(
                deleted_field="deleted_at",
                restore_action=True,
            )
        }
        config.update(overrides)
        return self.build_factory(**config)

    def build_simple_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "create_input": SimpleWidgetCreateDTO,
            "update_input": SimpleWidgetUpdateDTO,
            "partial_update_input": SimpleWidgetPatchDTO,
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_grouped_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_mapper": widget_to_response,
            "queryset": Widget.objects.order_by("id"),
            "read_only": True,
            "grouped_actions": (
                grouped_collection_action(
                    name="grouped",
                    query_dataclass=WidgetGroupQueryDTO,
                    response_dataclass=WidgetGroupResponseDTO,
                    handler=widget_group_response,
                    source_acl=GroupedCollectionSourceACL(
                        permission="app.widgets.read",
                        resource_ref_from_instance=lambda widget: (
                            "allowed"
                            if cast(Widget, widget).name.startswith("allow")
                            else "denied"
                        ),
                    ),
                ),
            ),
            "acl": ACLConfig(
                backend=SelectiveACLBackend(),
                actor_resolver=lambda request: "actor",
            ),
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_query_action_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_mapper": widget_to_response,
            "queryset": Widget.objects.order_by("id"),
            "read_only": True,
            "custom_actions": (
                collection_action(
                    name="search",
                    query_dataclass=WidgetQueryActionDTO,
                    response_dataclass=WidgetQueryActionResponseDTO,
                    handler=widget_query_action_response,
                    methods=("get",),
                ),
            ),
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_list_query_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_mapper": widget_to_response,
            "queryset": Widget.objects.order_by("id"),
            "read_only": True,
            "list_query": WidgetListQueryDTO,
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_bulk_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": Widget,
            "response_mapper": widget_to_response,
            "create_input": WidgetCreateDTO,
            "update_input": WidgetUpdateDTO,
            "partial_update_input": WidgetPatchDTO,
            "create_handler": self.create_widget,
            "update_handler": self.update_widget,
            "partial_update_handler": self.patch_widget,
            "queryset": Widget.objects.order_by("id"),
            "bulk_actions": (
                bulk_create_action(transaction_mode="best-effort"),
                bulk_patch_action(
                    input_dataclass=WidgetBulkPatchDTO,
                    transaction_mode="best-effort",
                ),
                bulk_delete_action(
                    input_dataclass=WidgetBulkDeleteDTO,
                    transaction_mode="best-effort",
                ),
            ),
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_nested_factory(
        self,
        *,
        mode: str = "replace",
        **overrides: object,
    ) -> CRUDFactory:
        config = {
            "model": NestedWidget,
            "response_dataclass": NestedWidgetResponseDTO,
            "create_input": NestedWidgetCreateDTO,
            "update_input": NestedWidgetUpdateDTO,
            "partial_update_input": NestedWidgetPatchDTO,
            "queryset": NestedWidget.objects.prefetch_related("children").order_by("id"),
            "nested_writes": [
                nested_relation(
                    field_name="children",
                    relation_name="children",
                    mode=cast(Any, mode),
                    match_by="id",
                )
            ],
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_parent_scoped_child_factory(
        self,
        **overrides: object,
    ) -> CRUDFactory:
        config = {
            "model": NestedWidgetChild,
            "response_dataclass": NestedWidgetChildResponseDTO,
            "create_input": NestedWidgetChildCreateDTO,
            "update_input": NestedWidgetChildUpdateDTO,
            "partial_update_input": NestedWidgetChildPatchDTO,
            "queryset": NestedWidgetChild.objects.select_related("widget").order_by("id"),
            "route": "children",
            "basename": "nested-widget-child",
            "parent_scope": parent_scope(
                parent_model=NestedWidget,
                url_prefix="nested-widgets/<int:widget_pk>",
                parent_lookup_url_kwarg="widget_pk",
                child_fk_field="widget",
            ),
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def build_filtered_related_factory(
        self,
        **overrides: object,
    ) -> CRUDFactory:
        config = {
            "response_dataclass": FilteredNestedWidgetResponseDTO,
            "queryset": NestedWidget.objects.order_by("id"),
            "route": "filtered-widgets",
            "basename": "filtered-widget",
        }
        config.update(overrides)
        return CRUDFactory.read_only(
            model=NestedWidget,
            **config,
        )

    def build_child_query_plan_factory(self, **overrides: object) -> CRUDFactory:
        config = {
            "model": NestedWidgetChild,
            "response_dataclass": NestedWidgetChildRelatedResponseDTO,
            "queryset": NestedWidgetChild.objects.order_by("id"),
            "read_only": True,
            "query_plan": auto_query_plan(),
        }
        config.update(overrides)
        return CRUDFactory(**config)

    def create_widget(self, dto: WidgetCreateDTO) -> Widget:
        self.created_payloads.append(dto)
        return Widget.objects.create(
            name=dto.name,
            count=dto.count,
            secret="not-returned",
        )

    def update_widget(self, instance: Widget, dto: WidgetUpdateDTO) -> Widget:
        self.updated_payloads.append(dto)
        instance.name = dto.name
        instance.count = dto.count
        instance.save()
        return instance

    def patch_widget(self, instance: Widget, dto: WidgetPatchDTO) -> Widget:
        self.patched_payloads.append(dto)
        if dto.name is not None:
            instance.name = dto.name
        if dto.count is not None:
            instance.count = dto.count
        instance.save()
        return instance

    def test_rejects_non_dataclass_input(self) -> None:
        with self.assertRaisesRegex(TypeError, "create_input must be a dataclass"):
            self.build_factory(create_input=dict)

    def test_rejects_required_partial_update_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "partial_update_input fields"):
            self.build_factory(partial_update_input=InvalidWidgetPatchDTO)

    def test_rejects_regex_validation_on_non_string_fields(self) -> None:
        with self.assertRaisesRegex(TypeError, "regex can only be used on str"):
            self.build_factory(create_input=InvalidRegexDTO)

    def test_rejects_range_validation_on_unsupported_fields(self) -> None:
        with self.assertRaisesRegex(TypeError, "range_ can only be used"):
            self.build_factory(create_input=InvalidRangeDTO)

    def test_rejects_length_validation_on_unsupported_fields(self) -> None:
        with self.assertRaisesRegex(TypeError, "length can only be used"):
            self.build_factory(create_input=InvalidLengthDTO)

    def test_rejects_response_mapper_without_return_annotation(self) -> None:
        with self.assertRaisesRegex(TypeError, "dataclass return annotation"):
            self.build_factory(response_mapper=widget_to_unannotated_response)

    def test_rejects_response_mapper_with_non_dataclass_return_annotation(self) -> None:
        with self.assertRaisesRegex(TypeError, "return annotation must be a dataclass"):
            self.build_factory(response_mapper=widget_to_non_dataclass_response)

    def test_rejects_unsupported_nested_response_dataclass_fields(self) -> None:
        with self.assertRaisesRegex(TypeError, "Unsupported response field type"):
            self.build_factory(response_mapper=widget_to_invalid_nested_response)

    def test_runtime_response_mapper_shape_error_is_clear(self) -> None:
        widget = Widget.objects.create(name="alpha", count=1)
        factory = self.build_factory(response_mapper=widget_to_wrong_runtime_response)

        with self.assertRaisesRegex(TypeError, "Got dict"):
            factory.to_response_data(widget)

    def test_runtime_response_mapper_rejects_dataclass_class_instead_of_instance(self) -> None:
        widget = Widget.objects.create(name="alpha", count=1)

        def wrong_mapper(instance: Widget) -> WidgetResponseDTO:
            _ = instance
            return cast(WidgetResponseDTO, WidgetResponseDTO)

        factory = self.build_factory(response_mapper=wrong_mapper)

        with self.assertRaisesRegex(TypeError, "dataclass instance"):
            factory.to_response_data(widget)

    def test_get_viewset_class_returns_model_viewset(self) -> None:
        viewset_class = self.build_factory().get_viewset_class()

        self.assertTrue(issubclass(viewset_class, ModelViewSet))

    def test_rejects_scoped_acl_list_without_resource_resolver(self) -> None:
        with self.assertRaisesRegex(TypeError, "Scoped list_action requires"):
            self.build_factory(
                acl=ACLConfig(
                    backend=FakeACLBackend(),
                    list_action=ACLActionConfig(permission="app.widgets.read"),
                )
            )

    def test_rejects_scoped_acl_create_without_input_resolver(self) -> None:
        with self.assertRaisesRegex(TypeError, "Scoped create_action requires"):
            self.build_factory(
                acl=ACLConfig(
                    backend=FakeACLBackend(),
                    create_action=ACLActionConfig(permission="app.widgets.create"),
                    resource_ref_from_instance=lambda widget: cast(Widget, widget).name,
                )
            )

    def test_auto_factory_create_update_patch_without_handlers_or_mapper(self) -> None:
        viewset_class = self.build_simple_factory().get_viewset_class()

        create_response = viewset_class.as_view({"post": "create"})(
            self.request_factory.post(
                "/widgets/",
                {"public_name": "alpha", "count": 3, "secret": "ignored"},
                format="json",
            )
        )
        widget_id = create_response.data["id"]
        update_response = viewset_class.as_view({"put": "update"})(
            self.request_factory.put(
                f"/widgets/{widget_id}/",
                {"public_name": "beta", "count": 8},
                format="json",
            ),
            pk=widget_id,
        )
        patch_response = viewset_class.as_view({"patch": "partial_update"})(
            self.request_factory.patch(
                f"/widgets/{widget_id}/",
                {"count": 9},
                format="json",
            ),
            pk=widget_id,
        )

        widget = Widget.objects.get(pk=widget_id)
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["public_name"], "alpha")
        self.assertEqual(update_response.data["public_name"], "beta")
        self.assertEqual(patch_response.data, {"id": widget_id, "public_name": "beta", "count": 9})
        self.assertEqual(widget.name, "beta")
        self.assertEqual(widget.count, 9)
        self.assertEqual(widget.secret, "")

    def test_auto_factory_uses_field_transformers_for_read_and_write(self) -> None:
        viewset_class = CRUDFactory(
            model=Widget,
            create_input=TransformWidgetCreateDTO,
            update_input=TransformWidgetUpdateDTO,
            partial_update_input=TransformWidgetPatchDTO,
        ).get_viewset_class()

        create_response = viewset_class.as_view({"post": "create"})(
            self.request_factory.post(
                "/widgets/",
                {"name": "alpha", "count_label": "count:3"},
                format="json",
            )
        )

        widget = Widget.objects.get(pk=create_response.data["id"])
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["count_label"], "count:3")
        self.assertEqual(widget.count, 3)

    def test_writable_fields_still_use_dataclass_validation(self) -> None:
        view = self.build_simple_factory().get_viewset_class().as_view({"post": "create"})

        response = view(
            self.request_factory.post(
                "/widgets/",
                {"public_name": "not valid", "count": 3},
                format="json",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("public_name", response.data)

    def test_writable_fields_reject_unknown_dto_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not define that DTO field"):
            self.build_simple_factory(writable_fields=["missing"])

    def test_writable_fields_reject_unknown_mapped_model_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.build_simple_factory(
                create_input=InvalidMappedFieldDTO,
                update_input=InvalidMappedFieldDTO,
                partial_update_input=InvalidMappedFieldDTO,
                writable_fields=["public_name"],
            )

    def test_writable_fields_reject_duplicate_model_targets(self) -> None:
        with self.assertRaisesRegex(ValueError, "both map to model field"):
            self.build_simple_factory(
                create_input=DuplicateMappedFieldDTO,
                update_input=DuplicateMappedFieldDTO,
                partial_update_input=DuplicateMappedFieldDTO,
                writable_fields=["first_name", "second_name"],
            )

    def test_viewset_exposes_response_serializer_for_schema_tools(self) -> None:
        viewset_class = self.build_factory().get_viewset_class()
        viewset = viewset_class()
        viewset.action = "retrieve"

        serializer_class = viewset.get_serializer_class()
        serializer = cast(serializers.Serializer, serializer_class())
        response_serializer_class = getattr(viewset_class, "response_serializer_class")
        request_serializer_classes = cast(
            dict[str, type[serializers.Serializer]],
            getattr(viewset_class, "request_serializer_classes"),
        )

        self.assertIs(serializer_class, response_serializer_class)
        self.assertEqual(
            set(serializer.fields),
            {"id", "name", "count", "label"},
        )
        self.assertEqual(
            set(request_serializer_classes),
            {"create", "update", "partial_update"},
        )

    def test_nested_response_serializer_documents_stats_dataclasses(self) -> None:
        viewset_class = self.build_stats_factory().get_viewset_class()
        response_serializer_class = cast(
            type[serializers.Serializer],
            getattr(viewset_class, "response_serializer_class"),
        )
        serializer = response_serializer_class()

        self.assertEqual(
            set(serializer.fields),
            {"id", "name", "availability", "scores"},
        )
        availability_serializer = cast(
            serializers.Serializer,
            serializer.fields["availability"],
        )
        scores_serializer = cast(serializers.Serializer, serializer.fields["scores"])
        self.assertEqual(
            set(availability_serializer.fields),
            {"online", "offline", "faulted"},
        )
        self.assertEqual(
            set(scores_serializer.fields),
            {"total", "average", "minimum", "maximum"},
        )

    def test_enum_summary_generates_count_fields_from_enum(self) -> None:
        self.assertEqual(
            [dataclass_field.name for dataclass_field in dataclass_fields(WidgetEnumAvailabilityStatsDTO)],
            ["online", "offline", "faulted"],
        )

    def test_enum_summary_counts_configured_values(self) -> None:
        widget = Widget.objects.create(name="alpha", count=2, secret="online")
        viewset_class = self.build_enum_stats_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/widgets/{widget.pk}/"),
            pk=widget.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "id": widget.pk,
                "name": "alpha",
                "availability": {
                    "online": 1,
                    "offline": 0,
                    "faulted": 0,
                },
            },
        )

    def test_enum_summary_markdown_docs_describe_histogram_fields(self) -> None:
        markdown = self.build_enum_stats_factory(route="widgets").render_markdown_docs(
            title="Widget Enum Factory",
            base_path="/api",
        )

        self.assertIn("Enum histogram summary: yes", markdown)
        self.assertIn("Enum lookup: root field `secret`", markdown)
        self.assertIn("Generated values: `online` -> `online`", markdown)

    def test_annotation_fields_appear_in_list_and_detail_responses(self) -> None:
        Widget.objects.create(name="alpha", count=2)
        busy = Widget.objects.create(name="beta", count=9)
        viewset_class = self.build_annotation_factory().get_viewset_class()

        list_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/")
        )
        detail_response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/widgets/{busy.pk}/"),
            pk=busy.pk,
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            list_response.data,
            [
                {
                    "id": ANY,
                    "name": "alpha",
                    "mirrored_count": 2,
                    "state_label": "idle",
                    "has_high_count": False,
                },
                {
                    "id": ANY,
                    "name": "beta",
                    "mirrored_count": 9,
                    "state_label": "busy",
                    "has_high_count": True,
                },
            ],
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.data,
            {
                "id": busy.pk,
                "name": "beta",
                "mirrored_count": 9,
                "state_label": "busy",
                "has_high_count": True,
            },
        )

    def test_annotation_metadata_validation_rejects_non_expression_values(self) -> None:
        with self.assertRaisesRegex(TypeError, "requires a Django expression"):
            self.build_annotation_factory(
                response_dataclass=InvalidWidgetAnnotationResponseDTO,
            )

    def test_latest_related_value_requires_relation_or_model_configuration(self) -> None:
        with self.assertRaisesRegex(TypeError, "requires either relation=... or both model=..."):
            self.build_latest_factory(
                response_dataclass=InvalidWidgetLatestResponseDTO,
            )

    def test_latest_related_value_appears_in_list_and_detail_responses(self) -> None:
        first = Widget.objects.create(name="alpha", count=2)
        second = Widget.objects.create(name="beta", count=9)
        WidgetReading.objects.create(widget=first, value=2, label="older")
        WidgetReading.objects.create(widget=first, value=7, label="newer")
        WidgetReading.objects.create(widget=second, value=11, label="latest")
        viewset_class = self.build_latest_factory().get_viewset_class()

        list_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/")
        )
        detail_response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/widgets/{first.pk}/"),
            pk=first.pk,
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            list_response.data,
            [
                {
                    "id": ANY,
                    "name": "alpha",
                    "latest_value": 7,
                    "latest_reading": {"value": 7, "label": "newer"},
                },
                {
                    "id": ANY,
                    "name": "beta",
                    "latest_value": 11,
                    "latest_reading": {"value": 11, "label": "latest"},
                },
            ],
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.data,
            {
                "id": first.pk,
                "name": "alpha",
                "latest_value": 7,
                "latest_reading": {"value": 7, "label": "newer"},
            },
        )

    def test_latest_related_value_uses_null_when_no_child_rows_exist(self) -> None:
        widget = Widget.objects.create(name="alpha", count=2)
        viewset_class = self.build_latest_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/widgets/{widget.pk}/"),
            pk=widget.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "id": widget.pk,
                "name": "alpha",
                "latest_value": None,
                "latest_reading": {"value": None, "label": None},
            },
        )

    def test_related_list_can_declare_filtered_queryset(self) -> None:
        widget = NestedWidget.objects.create(name="parent")
        NestedWidgetChild.objects.create(widget=widget, name="online-child", status="online")
        NestedWidgetChild.objects.create(widget=widget, name="offline-child", status="offline")
        viewset_class = self.build_filtered_related_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/filtered-widgets/{widget.pk}/"),
            pk=widget.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "id": widget.pk,
                "name": "parent",
                "children": [
                    {
                        "id": ANY,
                        "name": "online-child",
                        "status": "online",
                    }
                ],
            },
        )

    def test_related_list_prefetches_are_registered_on_generated_queryset(self) -> None:
        factory = self.build_filtered_related_factory()
        prefetch_lookups = factory.related_prefetches

        self.assertEqual(len(prefetch_lookups), 1)
        self.assertEqual(prefetch_lookups[0].prefetch_to, "children")

    def test_related_list_markdown_docs_include_prefetch_metadata(self) -> None:
        markdown = self.build_filtered_related_factory().render_markdown_docs(
            title="Filtered Widget Factory",
            base_path="/api",
        )

        self.assertIn("Related list source: `children`", markdown)
        self.assertIn(
            "Related list queryset: `NestedWidgetChild` with declarative prefetch",
            markdown,
        )

    def test_derive_query_plan_infers_forward_select_related_paths(self) -> None:
        factory = self.build_child_query_plan_factory()
        query_plan = derive_query_plan(
            model=NestedWidgetChild,
            response_mapper=factory.response_mapper,
            stat_specs=factory.stat_specs,
            annotation_specs=factory.annotation_specs,
        )

        self.assertEqual(query_plan.select_related, ("widget",))

    def test_auto_query_plan_is_applied_to_generated_queryset(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        child = NestedWidgetChild.objects.create(widget=parent, name="child", status="online")
        factory = self.build_child_query_plan_factory()
        viewset_class = factory.get_viewset_class()
        response = viewset_class.as_view({"get": "list"})(self.request_factory.get("/children/"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["widget_name"], "parent")
        self.assertEqual(factory.query_plan.select_related, ("widget",))
        self.assertEqual([item["id"] for item in response.data], [child.pk])

    def test_manual_queryset_is_preserved_when_auto_query_plan_is_enabled(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        hidden_parent = NestedWidget.objects.create(name="hidden-parent")
        visible = NestedWidgetChild.objects.create(widget=parent, name="visible", status="online")
        NestedWidgetChild.objects.create(widget=hidden_parent, name="hidden", status="offline")
        factory = self.build_child_query_plan_factory(
            queryset=NestedWidgetChild.objects.filter(name="visible").order_by("id"),
        )
        response = factory.get_viewset_class().as_view({"get": "list"})(
            self.request_factory.get("/children/")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [visible.pk])

    def test_query_plan_can_opt_out_of_auto_inference(self) -> None:
        factory = self.build_child_query_plan_factory(
            query_plan=QueryPlan(replace_auto=True),
        )

        self.assertEqual(factory.query_plan.select_related, ())
        self.assertEqual(factory.query_plan.prefetch_related, ())

    def test_query_plan_markdown_docs_include_select_and_prefetch_hints(self) -> None:
        markdown = self.build_filtered_related_factory().render_markdown_docs(
            title="Filtered Widget Factory",
            base_path="/api",
        )

        self.assertIn("## Query Plan", markdown)
        self.assertIn("`prefetch_related(...)`", markdown)
        self.assertIn("`children`", markdown)

    def test_factory_can_render_markdown_contract_docs(self) -> None:
        markdown = self.build_factory(route="widgets", basename="widget").render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("# Widget Factory", markdown)
        self.assertIn("`GET /api/widgets/`", markdown)
        self.assertIn("## Request DTOs", markdown)
        self.assertIn("`WidgetCreateDTO`", markdown)
        self.assertIn("`WidgetResponseDTO`", markdown)
        self.assertIn("## Error Responses", markdown)
        self.assertIn("400 Bad Request", markdown)
        self.assertIn('  "detail": "Locked connectors cannot be started."', markdown)
        self.assertIn("Filterable: `name`", markdown)
        self.assertIn("Orderable: `count`", markdown)

    def test_annotation_markdown_docs_label_annotated_response_fields(self) -> None:
        markdown = self.build_annotation_factory(route="widgets").render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("Annotation: declarative queryset annotation", markdown)

    def test_field_subresource_get_returns_raw_field_payload(self) -> None:
        widget = Widget.objects.create(
            name="alpha",
            count=1,
            metadata={"source": "seed", "enabled": True},
        )
        view = self.build_factory(
            field_subresources=[
                field_subresource(
                    field_name="metadata",
                    patch_mode="merge",
                )
            ]
        ).get_viewset_class().as_view({"get": "metadata"})

        response = view(self.request_factory.get(f"/widgets/{widget.pk}/metadata/"), pk=widget.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"source": "seed", "enabled": True})

    def test_field_subresource_patch_merge_updates_only_target_field(self) -> None:
        widget = Widget.objects.create(
            name="alpha",
            count=1,
            secret="keep-secret",
            metadata={"source": "seed", "enabled": True},
        )
        view = self.build_factory(
            field_subresources=[
                field_subresource(
                    field_name="metadata",
                    patch_mode="merge",
                )
            ]
        ).get_viewset_class().as_view({"patch": "metadata"})

        response = view(
            self.request_factory.patch(
                f"/widgets/{widget.pk}/metadata/",
                {"enabled": False, "note": "patched"},
                format="json",
            ),
            pk=widget.pk,
        )

        widget.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"source": "seed", "enabled": False, "note": "patched"},
        )
        self.assertEqual(widget.name, "alpha")
        self.assertEqual(widget.secret, "keep-secret")

    def test_field_subresource_markdown_docs_include_endpoint_contract(self) -> None:
        markdown = self.build_factory(
            route="widgets",
            basename="widget",
            field_subresources=[
                field_subresource(
                    field_name="metadata",
                    patch_mode="merge",
                )
            ],
        ).render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("## Field Subresource Endpoints", markdown)
        self.assertIn("`GET, PATCH /api/widgets/{pk}/metadata/`", markdown)
        self.assertIn("Raw payload type: `JSON object`", markdown)
        self.assertIn("PATCH mode: `merge`", markdown)

    def test_nested_create_writes_related_children(self) -> None:
        view = self.build_nested_factory().get_viewset_class().as_view({"post": "create"})

        response = view(
            self.request_factory.post(
                "/nested-widgets/",
                {
                    "name": "parent",
                    "children": [
                        {"name": "child-a", "status": "online"},
                        {"name": "child-b", "status": "offline"},
                    ],
                },
                format="json",
            )
        )

        created = NestedWidget.objects.get(pk=response.data["id"])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(created.children.count(), 2)
        self.assertEqual(
            [child["name"] for child in response.data["children"]],
            ["child-a", "child-b"],
        )

    def test_nested_full_update_replace_updates_creates_and_deletes_children(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        kept = NestedWidgetChild.objects.create(widget=parent, name="keep", status="online")
        NestedWidgetChild.objects.create(widget=parent, name="drop", status="offline")
        view = self.build_nested_factory(mode="replace").get_viewset_class().as_view(
            {"put": "update"}
        )

        response = view(
            self.request_factory.put(
                f"/nested-widgets/{parent.pk}/",
                {
                    "name": "parent-updated",
                    "children": [
                        {"id": kept.pk, "name": "keep-updated", "status": "faulted"},
                        {"name": "created", "status": "online"},
                    ],
                },
                format="json",
            ),
            pk=parent.pk,
        )

        parent.refresh_from_db()
        children = list(parent.children.order_by("id"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(parent.name, "parent-updated")
        self.assertEqual(
            [(child.name, child.status) for child in children],
            [("keep-updated", "faulted"), ("created", "online")],
        )

    def test_nested_patch_merge_updates_selected_child_without_deleting_others(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        first = NestedWidgetChild.objects.create(widget=parent, name="first", status="online")
        second = NestedWidgetChild.objects.create(widget=parent, name="second", status="offline")
        view = self.build_nested_factory(mode="merge").get_viewset_class().as_view(
            {"patch": "partial_update"}
        )

        response = view(
            self.request_factory.patch(
                f"/nested-widgets/{parent.pk}/",
                {"children": [{"id": first.pk, "status": "faulted"}]},
                format="json",
            ),
            pk=parent.pk,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(first.status, "faulted")
        self.assertEqual(second.status, "offline")

    def test_nested_patch_without_children_leaves_existing_children_untouched(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        NestedWidgetChild.objects.create(widget=parent, name="first", status="online")
        view = self.build_nested_factory(mode="merge").get_viewset_class().as_view(
            {"patch": "partial_update"}
        )

        response = view(
            self.request_factory.patch(
                f"/nested-widgets/{parent.pk}/",
                {"name": "renamed"},
                format="json",
            ),
            pk=parent.pk,
        )

        parent.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(parent.name, "renamed")
        self.assertEqual(parent.children.count(), 1)

    def test_nested_duplicate_child_match_keys_return_validation_error(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        child = NestedWidgetChild.objects.create(widget=parent, name="first", status="online")
        view = self.build_nested_factory(mode="merge").get_viewset_class().as_view(
            {"patch": "partial_update"}
        )

        response = view(
            self.request_factory.patch(
                f"/nested-widgets/{parent.pk}/",
                {
                    "children": [
                        {"id": child.pk, "status": "faulted"},
                        {"id": child.pk, "status": "offline"},
                    ]
                },
                format="json",
            ),
            pk=parent.pk,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("children", response.data)

    def test_nested_replace_requires_match_by_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires match_by"):
            CRUDFactory(
                model=NestedWidget,
                response_dataclass=NestedWidgetResponseDTO,
                create_input=NestedWidgetCreateDTO,
                update_input=NestedWidgetUpdateDTO,
                partial_update_input=NestedWidgetPatchDTO,
                nested_writes=[
                    nested_relation(
                        field_name="children",
                        relation_name="children",
                        mode="replace",
                    )
                ],
            )

    def test_parent_scoped_list_returns_only_children_for_parent(self) -> None:
        first_parent = NestedWidget.objects.create(name="first")
        second_parent = NestedWidget.objects.create(name="second")
        first_child = NestedWidgetChild.objects.create(
            widget=first_parent,
            name="first-child",
            status="online",
        )
        NestedWidgetChild.objects.create(
            widget=second_parent,
            name="second-child",
            status="offline",
        )
        view = self.build_parent_scoped_child_factory().get_viewset_class().as_view(
            {"get": "list"}
        )

        response = view(
            self.request_factory.get(f"/nested-widgets/{first_parent.pk}/children/"),
            widget_pk=first_parent.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            [
                {
                    "id": first_child.pk,
                    "widget_id": first_parent.pk,
                    "name": "first-child",
                    "status": "online",
                }
            ],
        )

    def test_parent_scoped_create_binds_parent_from_url(self) -> None:
        target_parent = NestedWidget.objects.create(name="target")
        conflicting_parent = NestedWidget.objects.create(name="conflict")
        view = self.build_parent_scoped_child_factory().get_viewset_class().as_view(
            {"post": "create"}
        )

        response = view(
            self.request_factory.post(
                f"/nested-widgets/{target_parent.pk}/children/",
                {
                    "widget_id": conflicting_parent.pk,
                    "name": "bound-child",
                    "status": "online",
                },
                format="json",
            ),
            widget_pk=target_parent.pk,
        )

        created_child = NestedWidgetChild.objects.get(pk=response.data["id"])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(created_child.widget_id, target_parent.pk)
        self.assertEqual(response.data["widget_id"], target_parent.pk)

    def test_parent_scoped_detail_rejects_child_from_different_parent(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        other_parent = NestedWidget.objects.create(name="other")
        other_child = NestedWidgetChild.objects.create(
            widget=other_parent,
            name="other-child",
            status="online",
        )
        view = self.build_parent_scoped_child_factory().get_viewset_class().as_view(
            {"get": "retrieve"}
        )

        response = view(
            self.request_factory.get(
                f"/nested-widgets/{parent.pk}/children/{other_child.pk}/"
            ),
            widget_pk=parent.pk,
            pk=other_child.pk,
        )

        self.assertEqual(response.status_code, 404)

    def test_parent_scoped_update_cannot_move_child_to_other_parent(self) -> None:
        parent = NestedWidget.objects.create(name="parent")
        other_parent = NestedWidget.objects.create(name="other")
        child = NestedWidgetChild.objects.create(
            widget=parent,
            name="bound-child",
            status="online",
        )
        view = self.build_parent_scoped_child_factory().get_viewset_class().as_view(
            {"put": "update"}
        )

        response = view(
            self.request_factory.put(
                f"/nested-widgets/{parent.pk}/children/{child.pk}/",
                {
                    "widget_id": other_parent.pk,
                    "name": "updated-child",
                    "status": "faulted",
                },
                format="json",
            ),
            widget_pk=parent.pk,
            pk=child.pk,
        )

        child.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(child.widget_id, parent.pk)
        self.assertEqual(child.name, "updated-child")
        self.assertEqual(response.data["widget_id"], parent.pk)

    def test_parent_scoped_router_is_not_available(self) -> None:
        with self.assertRaisesRegex(TypeError, "Parent-scoped factories do not expose a DRF router"):
            self.build_parent_scoped_child_factory().get_router()

    def test_parent_scoped_markdown_docs_include_nested_route(self) -> None:
        markdown = self.build_parent_scoped_child_factory().render_markdown_docs(
            title="Nested Child Factory",
            base_path="/api",
        )

        self.assertIn(
            "`GET /api/nested-widgets/<int:widget_pk>/children/`",
            markdown,
        )

    def test_grouped_action_registration_returns_collection_route(self) -> None:
        viewset_class = self.build_grouped_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "grouped"})(
            self.request_factory.get("/widgets/grouped/")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"buckets": [{"label": "all", "items": []}]})

    def test_grouped_action_reads_query_dto_from_query_params(self) -> None:
        captured: list[WidgetGroupQueryDTO] = []

        def handler(
            widgets: models.QuerySet[Widget] | Sequence[Widget],
            query: WidgetGroupQueryDTO,
        ) -> WidgetGroupResponseDTO:
            _ = widgets
            captured.append(query)
            return WidgetGroupResponseDTO(buckets=[])

        viewset_class = self.build_grouped_factory(
            grouped_actions=(
                grouped_collection_action(
                    name="grouped",
                    query_dataclass=WidgetGroupQueryDTO,
                    response_dataclass=WidgetGroupResponseDTO,
                    handler=handler,
                ),
            )
        ).get_viewset_class()

        response = viewset_class.as_view({"get": "grouped"})(
            self.request_factory.get("/widgets/grouped/?name=alpha&count=3&label=beta")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            captured,
            [WidgetGroupQueryDTO(name="alpha", count=3, label="beta")],
        )

    def test_grouped_action_applies_source_filter_and_order_specs(self) -> None:
        Widget.objects.create(name="beta", count=1)
        Widget.objects.create(name="alpha", count=9)
        Widget.objects.create(name="alphabet", count=8)
        captured_names: list[str] = []

        def handler(
            widgets: models.QuerySet[Widget] | Sequence[Widget],
            query: WidgetGroupQueryDTO,
        ) -> WidgetGroupResponseDTO:
            _ = query
            captured_names.extend(widget.name for widget in widgets)
            return WidgetGroupResponseDTO(buckets=[])

        viewset_class = self.build_grouped_factory(
            grouped_actions=(
                grouped_collection_action(
                    name="grouped",
                    query_dataclass=WidgetGroupQueryDTO,
                    response_dataclass=WidgetGroupResponseDTO,
                    handler=handler,
                ),
            ),
            acl=ACLConfig(backend=FakeACLBackend(), actor_resolver=lambda request: "actor"),
        ).get_viewset_class()

        response = viewset_class.as_view({"get": "grouped"})(
            self.request_factory.get(
                "/widgets/grouped/?name__icontains=alpha&ordering=-label"
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_names, ["alphabet", "alpha"])

    def test_grouped_action_filters_unauthorized_source_rows_before_grouping(self) -> None:
        Widget.objects.create(name="allow-one", count=1)
        Widget.objects.create(name="deny-two", count=2)
        captured_names: list[str] = []

        def handler(
            widgets: models.QuerySet[Widget] | Sequence[Widget],
            query: WidgetGroupQueryDTO,
        ) -> WidgetGroupResponseDTO:
            _ = query
            captured_names.extend(widget.name for widget in widgets)
            return WidgetGroupResponseDTO(buckets=[])

        viewset_class = self.build_grouped_factory(
            grouped_actions=(
                grouped_collection_action(
                    name="grouped",
                    query_dataclass=WidgetGroupQueryDTO,
                    response_dataclass=WidgetGroupResponseDTO,
                    handler=handler,
                    source_acl=GroupedCollectionSourceACL(
                        permission="app.widgets.read",
                        resource_ref_from_instance=lambda widget: (
                            "allowed"
                            if cast(Widget, widget).name.startswith("allow")
                            else "denied"
                        ),
                    ),
                ),
            )
        ).get_viewset_class()

        response = viewset_class.as_view({"get": "grouped"})(
            self.request_factory.get("/widgets/grouped/")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_names, ["allow-one"])

    def test_grouped_action_markdown_docs_include_query_and_response_contracts(self) -> None:
        markdown = self.build_grouped_factory(route="widgets").render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("## Grouped Collection Actions", markdown)
        self.assertIn("`GET /api/widgets/grouped/`", markdown)
        self.assertIn("`WidgetGroupQueryDTO`", markdown)
        self.assertIn("`WidgetGroupResponseDTO`", markdown)

    def test_list_query_dto_filters_searches_and_excludes_queryset(self) -> None:
        Widget.objects.create(name="alpha", count=2, secret="needle")
        Widget.objects.create(name="beta", count=4, secret="needle")
        Widget.objects.create(name="gamma", count=6, secret="other")
        viewset_class = self.build_list_query_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get(
                "/widgets/?search=needle&min_count=3&exclude_name=alp"
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            [
                {
                    "id": ANY,
                    "name": "beta",
                    "count": 4,
                    "label": "beta:4",
                }
            ],
        )

    def test_list_query_dto_supports_list_values_and_ordering(self) -> None:
        Widget.objects.create(name="alpha", count=2)
        Widget.objects.create(name="beta", count=7)
        Widget.objects.create(name="gamma", count=4)
        viewset_class = self.build_list_query_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?names=alpha&names=beta&sort=-count")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["name"] for item in response.data],
            ["beta", "alpha"],
        )

    def test_list_query_dto_invalid_query_params_return_400(self) -> None:
        viewset_class = self.build_list_query_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?min_count=oops")
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("min_count", response.data)

    def test_list_query_markdown_docs_include_advanced_query_contract(self) -> None:
        markdown = self.build_list_query_factory(route="widgets").render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("### Advanced List Query DTO", markdown)
        self.assertIn("`WidgetListQueryDTO`", markdown)
        self.assertIn("List query search across", markdown)

    def test_query_collection_action_reads_query_params_and_ignores_body(self) -> None:
        Widget.objects.create(name="alpha", count=1)
        Widget.objects.create(name="alphabet", count=8)
        Widget.objects.create(name="beta", count=9)
        viewset_class = self.build_query_action_factory().get_viewset_class()

        request = self.request_factory.generic(
            "GET",
            "/widgets/search/?name=alpha&min_count=5",
            data='{"name":"beta","min_count":100}',
            content_type="application/json",
        )
        response = viewset_class.as_view({"get": "search"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "total": 1,
                "items": [{"id": ANY, "name": "alphabet"}],
            },
        )

    def test_query_collection_action_markdown_docs_include_query_contract(self) -> None:
        markdown = self.build_query_action_factory(route="widgets").render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("### `search`", markdown)
        self.assertIn("- Query DTO:", markdown)
        self.assertIn("`WidgetQueryActionDTO`", markdown)
        self.assertIn("`WidgetQueryActionResponseDTO`", markdown)

    def test_query_collection_action_rejects_non_get_methods(self) -> None:
        with self.assertRaisesRegex(ValueError, "only supports methods=\\('get',\\)"):
            self.build_query_action_factory(
                custom_actions=(
                    collection_action(
                        name="search",
                        query_dataclass=WidgetQueryActionDTO,
                        response_dataclass=WidgetQueryActionResponseDTO,
                        handler=widget_query_action_response,
                        methods=("post",),
                    ),
                )
            )

    def test_collection_action_requires_exactly_one_request_contract(self) -> None:
        with self.assertRaisesRegex(TypeError, "exactly one of input_dataclass or query_dataclass"):
            collection_action(
                name="broken",
                input_dataclass=WidgetCreateDTO,
                query_dataclass=WidgetQueryActionDTO,
                response_dataclass=WidgetQueryActionResponseDTO,
                handler=cast(Any, widget_query_action_response),
            )

    def test_bulk_create_best_effort_returns_structured_result(self) -> None:
        view = self.build_bulk_factory().get_viewset_class().as_view({"post": "bulk_create"})

        response = view(
            self.request_factory.post(
                "/widgets/bulk-create/",
                [
                    {"name": "alpha", "count": 3},
                    {"name": "beta", "count": 100},
                ],
                format="json",
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["failed"], 1)
        self.assertFalse(response.data["rolled_back"])
        self.assertEqual(Widget.objects.count(), 1)

    def test_bulk_create_atomic_rolls_back_all_rows(self) -> None:
        view = self.build_bulk_factory(
            bulk_actions=(bulk_create_action(transaction_mode="atomic"),)
        ).get_viewset_class().as_view({"post": "bulk_create"})

        response = view(
            self.request_factory.post(
                "/widgets/bulk-create/",
                [
                    {"name": "alpha", "count": 3},
                    {"name": "beta", "count": 100},
                ],
                format="json",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data["rolled_back"])
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["failed"], 1)
        self.assertEqual(Widget.objects.count(), 0)

    def test_bulk_patch_updates_many_rows(self) -> None:
        first = Widget.objects.create(name="alpha", count=1)
        second = Widget.objects.create(name="beta", count=3)
        view = self.build_bulk_factory().get_viewset_class().as_view({"patch": "bulk_patch"})

        response = view(
            self.request_factory.patch(
                "/widgets/bulk-patch/",
                [
                    {"id": first.pk, "count": 8},
                    {"id": second.pk, "name": "gamma"},
                ],
                format="json",
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.count, 8)
        self.assertEqual(second.name, "gamma")

    def test_bulk_delete_deletes_many_rows(self) -> None:
        first = Widget.objects.create(name="alpha", count=1)
        second = Widget.objects.create(name="beta", count=3)
        view = self.build_bulk_factory().get_viewset_class().as_view({"delete": "bulk_delete"})

        response = view(
            self.request_factory.delete(
                "/widgets/bulk-delete/",
                [
                    {"id": first.pk},
                    {"id": second.pk},
                ],
                format="json",
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted"], 2)
        self.assertFalse(Widget.objects.exists())

    def test_bulk_patch_reports_acl_row_failures_in_best_effort_mode(self) -> None:
        allowed = Widget.objects.create(name="allowed", count=1)
        denied = Widget.objects.create(name="denied", count=3)
        view = self.build_bulk_factory(
            bulk_actions=(
                bulk_patch_action(
                    input_dataclass=WidgetBulkPatchDTO,
                    transaction_mode="best-effort",
                ),
            ),
            acl=ACLConfig(
                backend=SelectiveACLBackend(),
                actor_resolver=lambda request: "actor",
                partial_update_action=ACLActionConfig(permission="app.widgets.patch"),
                resource_ref_from_instance=lambda widget: cast(Widget, widget).name,
            ),
        ).get_viewset_class().as_view({"patch": "bulk_patch"})

        response = view(
            self.request_factory.patch(
                "/widgets/bulk-patch/",
                [
                    {"id": allowed.pk, "count": 8},
                    {"id": denied.pk, "count": 9},
                ],
                format="json",
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        self.assertEqual(response.data["failed"], 1)
        allowed.refresh_from_db()
        denied.refresh_from_db()
        self.assertEqual(allowed.count, 8)
        self.assertEqual(denied.count, 3)

    def test_bulk_markdown_docs_include_row_and_result_contracts(self) -> None:
        markdown = self.build_bulk_factory(route="widgets").render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("## Bulk Operations", markdown)
        self.assertIn("### `bulk_create`", markdown)
        self.assertIn("`BulkMutationResultDTO`", markdown)

    def test_grouped_action_requires_factory_acl_when_source_acl_is_used(self) -> None:
        with self.assertRaisesRegex(TypeError, "uses source_acl, but the factory does not define acl"):
            self.build_grouped_factory(acl=None)

    def test_grouped_action_rejects_non_get_methods(self) -> None:
        with self.assertRaisesRegex(ValueError, "only supports methods=\\('get',\\)"):
            self.build_grouped_factory(
                grouped_actions=(
                    grouped_collection_action(
                        name="grouped",
                        query_dataclass=WidgetGroupQueryDTO,
                        response_dataclass=WidgetGroupResponseDTO,
                        handler=widget_group_response,
                        methods=("post",),
                    ),
                )
            )

    def test_app_defaults_use_model_app_label_and_model_name(self) -> None:
        factory = self.build_factory()

        self.assertEqual(factory.app_name, "tests")
        self.assertEqual(factory.route, "widget")
        self.assertEqual(factory.basename, "widget")

    def test_router_registers_viewset_for_app_urls(self) -> None:
        router = self.build_factory(route="widgets", basename="inventory-widget").get_router()

        self.assertIsInstance(router, SimpleRouter)
        self.assertEqual(len(router.registry), 1)
        self.assertEqual(router.registry[0][0], "widgets")
        self.assertEqual(router.registry[0][2], "inventory-widget")
        self.assertEqual(
            pattern_names(router.urls),
            {"inventory-widget-list", "inventory-widget-detail"},
        )

    def test_get_urlpatterns_returns_router_urls(self) -> None:
        urlpatterns = self.build_factory(route="widgets").get_urlpatterns()

        self.assertEqual(
            pattern_names(urlpatterns),
            {"widget-list", "widget-detail"},
        )

    def test_get_app_urlconf_returns_include_ready_tuple(self) -> None:
        urlconf = self.build_factory(
            app_name="inventory",
            route="widgets",
            basename="widget",
        ).get_app_urlconf(namespace="inventory-api")

        urlpatterns, app_name, namespace = urlconf
        self.assertEqual(app_name, "inventory")
        self.assertEqual(namespace, "inventory-api")
        self.assertEqual(
            pattern_names(urlpatterns),
            {"widget-list", "widget-detail"},
        )

    def test_create_validates_calls_handler_and_returns_response_dto(self) -> None:
        view = self.build_factory().get_viewset_class().as_view({"post": "create"})
        request = self.request_factory.post(
            "/widgets/",
            {"name": "alpha", "count": 3, "secret": "ignored"},
            format="json",
        )

        response = view(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.created_payloads), 1)
        self.assertEqual(self.created_payloads[0], WidgetCreateDTO(name="alpha", count=3))
        self.assertEqual(
            response.data,
            {
                "id": response.data["id"],
                "name": "alpha",
                "count": 3,
                "label": "alpha:3",
            },
        )
        self.assertNotIn("secret", response.data)

    def test_list_and_retrieve_return_response_dto_fields(self) -> None:
        widget = Widget.objects.create(name="beta", count=4, secret="hidden")
        viewset_class = self.build_factory().get_viewset_class()

        list_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/")
        )
        detail_response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/widgets/{widget.pk}/"),
            pk=widget.pk,
        )

        expected = {"id": cast(int, widget.pk), "name": "beta", "count": 4, "label": "beta:4"}
        self.assertEqual(list_response.data, [expected])
        self.assertEqual(detail_response.data, expected)
        self.assertNotIn("secret", list_response.data[0])

    def test_list_can_filter_by_filterable_response_field(self) -> None:
        Widget.objects.create(name="match", count=1)
        Widget.objects.create(name="skip", count=2)
        viewset_class = self.build_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?name=match")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.data], ["match"])

    def test_list_can_use_richer_filter_lookups(self) -> None:
        Widget.objects.create(name="alpha", count=1)
        Widget.objects.create(name="alphabet", count=8)
        Widget.objects.create(name="omega", count=9)
        viewset_class = self.build_factory().get_viewset_class()

        text_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?name__icontains=alpha")
        )
        range_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?count__gte=8&count__lte=9")
        )
        in_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?name__in=alpha,omega")
        )

        self.assertEqual(
            [item["name"] for item in text_response.data],
            ["alpha", "alphabet"],
        )
        self.assertEqual(
            [item["name"] for item in range_response.data],
            ["alphabet", "omega"],
        )
        self.assertEqual(
            [item["name"] for item in in_response.data],
            ["alpha", "omega"],
        )

    def test_list_can_order_by_orderable_response_fields(self) -> None:
        Widget.objects.create(name="middle", count=3)
        Widget.objects.create(name="last", count=1)
        Widget.objects.create(name="first", count=9)
        viewset_class = self.build_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?ordering=-count,name")
        )

        self.assertEqual(
            [item["name"] for item in response.data],
            ["first", "middle", "last"],
        )

    def test_invalid_ordering_returns_validation_error(self) -> None:
        Widget.objects.create(name="alpha", count=1)
        viewset_class = self.build_factory().get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/?ordering=secret")
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ordering", response.data)

    def test_read_only_factory_allows_reads_and_rejects_writes(self) -> None:
        Widget.objects.create(name="alpha", count=1)
        viewset_class = CRUDFactory.read_only(
            model=Widget,
            response_mapper=widget_to_response,
        ).get_viewset_class()

        list_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/")
        )
        create_response = viewset_class.as_view({"post": "create"})(
            self.request_factory.post(
                "/widgets/",
                {"name": "beta", "count": 1},
                format="json",
            )
        )

        self.assertEqual([item["name"] for item in list_response.data], ["alpha"])
        self.assertEqual(create_response.status_code, 405)
        self.assertEqual(getattr(viewset_class, "request_serializer_classes"), {})

    def test_update_validates_full_dto_and_calls_handler(self) -> None:
        widget = Widget.objects.create(name="old", count=1)
        view = self.build_factory().get_viewset_class().as_view({"put": "update"})
        request = self.request_factory.put(
            f"/widgets/{widget.pk}/",
            {"name": "new", "count": 8},
            format="json",
        )

        response = view(request, pk=widget.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.updated_payloads, [WidgetUpdateDTO(name="new", count=8)])
        self.assertEqual(response.data["label"], "new:8")

    def test_partial_update_validates_patch_dto_and_calls_handler(self) -> None:
        widget = Widget.objects.create(name="old", count=1)
        view = self.build_factory().get_viewset_class().as_view(
            {"patch": "partial_update"}
        )
        request = self.request_factory.patch(
            f"/widgets/{widget.pk}/",
            {"count": 9},
            format="json",
        )

        response = view(request, pk=widget.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.patched_payloads, [WidgetPatchDTO(name=None, count=9)])
        self.assertEqual(response.data["label"], "old:9")

    def test_delete_uses_default_destroy(self) -> None:
        widget = Widget.objects.create(name="gone", count=1)
        view = self.build_factory().get_viewset_class().as_view({"delete": "destroy"})

        response = view(self.request_factory.delete(f"/widgets/{widget.pk}/"), pk=widget.pk)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Widget.objects.filter(pk=widget.pk).exists())

    def test_soft_delete_lifecycle_marks_row_as_archived_instead_of_deleting(self) -> None:
        widget = Widget.objects.create(name="gone", count=1)
        view = self.build_soft_delete_factory().get_viewset_class().as_view({"delete": "destroy"})

        response = view(self.request_factory.delete(f"/widgets/{widget.pk}/"), pk=widget.pk)

        widget.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(widget.deleted_at)

    def test_soft_delete_lifecycle_hides_archived_rows_from_default_list(self) -> None:
        visible = Widget.objects.create(name="alpha", count=1)
        archived = Widget.objects.create(name="omega", count=9, deleted_at=dt.datetime.now(dt.timezone.utc))
        view = self.build_soft_delete_factory().get_viewset_class().as_view({"get": "list"})

        response = view(self.request_factory.get("/widgets/"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [visible.pk])
        self.assertNotIn(archived.pk, [item["id"] for item in response.data])

    def test_soft_delete_lifecycle_can_include_archived_rows_on_list(self) -> None:
        visible = Widget.objects.create(name="alpha", count=1)
        archived = Widget.objects.create(name="omega", count=9, deleted_at=dt.datetime.now(dt.timezone.utc))
        view = self.build_soft_delete_factory().get_viewset_class().as_view({"get": "list"})

        response = view(self.request_factory.get("/widgets/?include_archived=true"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.data],
            [visible.pk, archived.pk],
        )

    def test_soft_delete_lifecycle_restore_action_reactivates_archived_row(self) -> None:
        archived = Widget.objects.create(
            name="omega",
            count=9,
            deleted_at=dt.datetime.now(dt.timezone.utc),
        )
        view = self.build_soft_delete_factory().get_viewset_class().as_view({"post": "restore"})

        response = view(
            self.request_factory.post(f"/widgets/{archived.pk}/restore/", {}, format="json"),
            pk=archived.pk,
        )

        archived.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(archived.deleted_at)
        self.assertEqual(response.data["id"], archived.pk)

    def test_soft_delete_lifecycle_hides_archived_detail_and_update_routes(self) -> None:
        archived = Widget.objects.create(
            name="omega",
            count=9,
            deleted_at=dt.datetime.now(dt.timezone.utc),
        )
        retrieve_view = self.build_soft_delete_factory().get_viewset_class().as_view(
            {"get": "retrieve"}
        )
        patch_view = self.build_soft_delete_factory().get_viewset_class().as_view(
            {"patch": "partial_update"}
        )

        retrieve_response = retrieve_view(
            self.request_factory.get(f"/widgets/{archived.pk}/"),
            pk=archived.pk,
        )
        patch_response = patch_view(
            self.request_factory.patch(
                f"/widgets/{archived.pk}/",
                {"count": 8},
                format="json",
            ),
            pk=archived.pk,
        )

        self.assertEqual(retrieve_response.status_code, 404)
        self.assertEqual(patch_response.status_code, 404)

    def test_soft_delete_markdown_docs_describe_lifecycle_contract(self) -> None:
        markdown = self.build_soft_delete_factory(
            route="widgets",
            basename="widget",
        ).render_markdown_docs(
            title="Widget Factory",
            base_path="/api",
        )

        self.assertIn("## Lifecycle", markdown)
        self.assertIn("Mode: `timestamp-delete`", markdown)
        self.assertIn("Restore action: `POST /.../restore/`", markdown)
        self.assertIn("Include archived query param: `include_archived`", markdown)

    def test_soft_delete_lifecycle_validation_rejects_non_datetime_field(self) -> None:
        with self.assertRaisesRegex(TypeError, "soft_delete_lifecycle requires a DateTimeField"):
            self.build_factory(lifecycle=soft_delete_lifecycle(deleted_field="count"))

    def test_invalid_payload_returns_drf_validation_errors(self) -> None:
        view = self.build_factory().get_viewset_class().as_view({"post": "create"})

        response = view(
            self.request_factory.post(
                "/widgets/",
                {"name": "missing-count"},
                format="json",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("count", response.data)

    def test_regex_validation_returns_drf_validation_error(self) -> None:
        view = self.build_factory().get_viewset_class().as_view({"post": "create"})

        response = view(
            self.request_factory.post(
                "/widgets/",
                {"name": "not valid", "count": 1},
                format="json",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_range_validation_returns_drf_validation_error(self) -> None:
        view = self.build_factory().get_viewset_class().as_view({"post": "create"})

        response = view(
            self.request_factory.post(
                "/widgets/",
                {"name": "valid", "count": 11},
                format="json",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("count", response.data)

    def test_choices_validation_returns_drf_validation_error(self) -> None:
        view = self.build_factory().get_viewset_class().as_view({"post": "create"})

        response = view(
            self.request_factory.post(
                "/widgets/",
                {"name": "valid", "count": 2},
                format="json",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("count", response.data)

    def test_advanced_serializer_validators_cover_float_date_and_list(self) -> None:
        serializer_class = build_serializer_from_dataclass(
            AdvancedValidationDTO,
            name="AdvancedValidationSerializer",
        )

        invalid_serializer = serializer_class(
            data={
                "ratio": 1.1,
                "starts_on": "2025-12-31",
                "tags": ["a", "b", "c"],
            }
        )
        valid_serializer = serializer_class(
            data={
                "ratio": 0.5,
                "starts_on": "2026-01-01",
                "tags": ["a", "b"],
            }
        )

        self.assertFalse(invalid_serializer.is_valid())
        self.assertIn("ratio", invalid_serializer.errors)
        self.assertIn("starts_on", invalid_serializer.errors)
        self.assertIn("tags", invalid_serializer.errors)
        self.assertTrue(valid_serializer.is_valid(), valid_serializer.errors)

    def test_custom_queryset_lookup_and_permissions_are_applied(self) -> None:
        visible = Widget.objects.create(name="visible", count=1)
        Widget.objects.create(name="hidden", count=2)

        viewset_class = self.build_factory(
            queryset=Widget.objects.filter(name="visible"),
            lookup_field="id",
            lookup_url_kwarg="widget_id",
            permission_classes=[CustomPermission],
        ).get_viewset_class()

        response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/")
        )

        self.assertEqual(viewset_class.lookup_field, "id")
        self.assertEqual(viewset_class.lookup_url_kwarg, "widget_id")
        self.assertEqual(viewset_class.permission_classes, (CustomPermission,))
        self.assertEqual([item["id"] for item in response.data], [cast(int, visible.pk)])

    def test_stat_specs_are_discovered_from_nested_response_dataclasses(self) -> None:
        factory = self.build_stats_factory()

        self.assertEqual(
            [stat_spec.path for stat_spec in factory.stat_specs],
            [
                ("availability", "online"),
                ("availability", "offline"),
                ("availability", "faulted"),
                ("scores", "total"),
                ("scores", "average"),
                ("scores", "minimum"),
                ("scores", "maximum"),
            ],
        )

    def test_list_and_retrieve_return_embedded_aggregate_stats(self) -> None:
        widget = Widget.objects.create(name="stats", count=6)
        other_widget = Widget.objects.create(name="other", count=1, secret="faulted")
        viewset_class = self.build_stats_factory().get_viewset_class()

        list_response = viewset_class.as_view({"get": "list"})(
            self.request_factory.get("/widgets/")
        )
        detail_response = viewset_class.as_view({"get": "retrieve"})(
            self.request_factory.get(f"/widgets/{widget.pk}/"),
            pk=widget.pk,
        )

        expected = {
            "id": cast(int, widget.pk),
            "name": "stats",
            "availability": {"online": 1, "offline": 0, "faulted": 0},
            "scores": {"total": 6, "average": 6.0, "minimum": 6, "maximum": 6},
        }
        response_by_id = {item["id"]: item for item in list_response.data}
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(response_by_id[widget.pk], expected)
        self.assertEqual(detail_response.data, expected)
        self.assertEqual(response_by_id[other_widget.pk]["availability"]["faulted"], 1)

    def test_write_responses_refetch_embedded_aggregate_stats(self) -> None:
        def create_widget_with_event(dto: WidgetCreateDTO) -> Widget:
            return self.create_widget(dto)

        def update_widget_with_event(
            instance: Widget,
            dto: WidgetUpdateDTO,
        ) -> Widget:
            return self.update_widget(instance, dto)

        def patch_widget_with_event(instance: Widget, dto: WidgetPatchDTO) -> Widget:
            instance.secret = "faulted"
            instance.save(update_fields=["secret"])
            return self.patch_widget(instance, dto)

        viewset_class = self.build_stats_factory(
            create_handler=create_widget_with_event,
            update_handler=update_widget_with_event,
            partial_update_handler=patch_widget_with_event,
        ).get_viewset_class()

        create_response = viewset_class.as_view({"post": "create"})(
            self.request_factory.post(
                "/widgets/",
                {"name": "alpha", "count": 3},
                format="json",
            )
        )
        widget_id = create_response.data["id"]
        update_response = viewset_class.as_view({"put": "update"})(
            self.request_factory.put(
                f"/widgets/{widget_id}/",
                {"name": "alpha", "count": 8},
                format="json",
            ),
            pk=widget_id,
        )
        patch_response = viewset_class.as_view({"patch": "partial_update"})(
            self.request_factory.patch(
                f"/widgets/{widget_id}/",
                {"count": 9},
                format="json",
            ),
            pk=widget_id,
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(
            create_response.data["availability"],
            {"online": 0, "offline": 1, "faulted": 0},
        )
        self.assertEqual(update_response.data["availability"]["online"], 1)
        self.assertEqual(patch_response.data["availability"]["faulted"], 1)
        self.assertEqual(patch_response.data["scores"]["total"], 9)

    def test_to_response_data_applies_embedded_aggregate_stats(self) -> None:
        widget = Widget.objects.create(name="helper", count=1)
        widget.count = 7
        widget.secret = "faulted"
        widget.save(update_fields=["count", "secret"])

        data = self.build_stats_factory().to_response_data(widget)

        self.assertEqual(
            data,
            {
                "id": cast(int, widget.pk),
                "name": "helper",
                "availability": {"online": 1, "offline": 0, "faulted": 1},
                "scores": {"total": 7, "average": 7.0, "minimum": 7, "maximum": 7},
            },
        )


if __name__ == "__main__":
    unittest.main()
