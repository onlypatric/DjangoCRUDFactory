from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production_app", "0002_supplier_inventoryitem_supplier_stocklevel"),
    ]

    operations = [
        migrations.CreateModel(
            name="StatusReading",
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
                ("state", models.CharField(max_length=20)),
                ("duration", models.PositiveIntegerField(default=0)),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_readings",
                        to="production_app.inventoryitem",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
