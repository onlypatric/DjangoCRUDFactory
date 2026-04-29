from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="InventoryItem",
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
                ("quantity", models.PositiveIntegerField(default=0)),
                ("internal_code", models.CharField(blank=True, default="", max_length=40)),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
