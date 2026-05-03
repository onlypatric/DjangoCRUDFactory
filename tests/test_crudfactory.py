from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

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
from django.db.models import Q
from rest_framework.permissions import BasePermission
from rest_framework.routers import SimpleRouter
from rest_framework import serializers
from rest_framework.test import APIRequestFactory
from rest_framework.viewsets import ModelViewSet

django.setup()

from crudfactory import (
    ACLActionConfig,
    ACLConfig,
    ACLBackend,
    CRUDFactory,
    GroupedCollectionSourceACL,
    avg_stat,
    choices,
    grouped_collection_action,
    count_stat,
    field_subresource,
    filterable,
    length,
    max_stat,
    min_stat,
    model_field,
    nested_relation,
    orderable,
    range_,
    regex,
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


class CRUDFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(Widget)
            schema_editor.create_model(NestedWidget)
            schema_editor.create_model(NestedWidgetChild)

    @classmethod
    def tearDownClass(cls) -> None:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(NestedWidgetChild)
            schema_editor.delete_model(NestedWidget)
            schema_editor.delete_model(Widget)
        super().tearDownClass()

    def setUp(self) -> None:
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
