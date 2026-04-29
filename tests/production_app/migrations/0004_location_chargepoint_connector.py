from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production_app", "0003_statusreading"),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                ("city", models.CharField(max_length=80)),
                ("address", models.CharField(max_length=160)),
                ("postal_code", models.CharField(max_length=20)),
                ("country", models.CharField(default="Italy", max_length=40)),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Chargepoint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("serial_number", models.CharField(max_length=80, unique=True)),
                ("software_version", models.CharField(max_length=40)),
                ("vendor_name", models.CharField(blank=True, default="", max_length=80)),
                (
                    "max_power_kw",
                    models.DecimalField(decimal_places=2, default=0, max_digits=8),
                ),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chargepoints",
                        to="production_app.location",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Connector",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=80)),
                ("connector_type", models.CharField(max_length=40)),
                ("status", models.CharField(max_length=20)),
                (
                    "power_kw",
                    models.DecimalField(decimal_places=2, default=0, max_digits=8),
                ),
                ("current_a", models.PositiveIntegerField(default=0)),
                ("voltage_v", models.PositiveIntegerField(default=0)),
                (
                    "chargepoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="connectors",
                        to="production_app.chargepoint",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
