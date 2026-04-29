from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production_app", "0004_location_chargepoint_connector"),
    ]

    operations = [
        migrations.AddField(
            model_name="connector",
            name="is_locked",
            field=models.BooleanField(default=False),
        ),
    ]
