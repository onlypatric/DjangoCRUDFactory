from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production_app", "0005_connector_is_locked"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="location",
            name="description",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="location",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="location",
            name="network_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="location",
            name="province",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="chargepoint",
            name="active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="chargepoint",
            name="last_heartbeat",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chargepoint",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="chargepoint",
            name="ocpp_status",
            field=models.CharField(default="Offline", max_length=24),
        ),
        migrations.AddField(
            model_name="chargepoint",
            name="remote_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="connector",
            name="error_code",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="connector",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="connector",
            name="stats",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="connector",
            name="vendor_error_code",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
