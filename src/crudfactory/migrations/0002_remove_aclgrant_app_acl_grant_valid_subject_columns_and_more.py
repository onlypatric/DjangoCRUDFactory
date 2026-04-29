from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("crudfactory", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="aclgrant",
            name="app_acl_grant_valid_subject_columns",
        ),
        migrations.AddConstraint(
            model_name="aclgrant",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        Q(subject_kind="user")
                        & Q(subject_user__isnull=False)
                        & Q(subject_group__isnull=True)
                    )
                    | (
                        Q(subject_kind="group")
                        & Q(subject_group__isnull=False)
                        & Q(subject_user__isnull=True)
                    )
                ),
                name="app_acl_grant_valid_subject_columns",
            ),
        ),
    ]
