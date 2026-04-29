from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from django.core.management.base import BaseCommand, CommandError

from ...acl_bootstrap import ACLBootstrapper, ACLPermissionSeed, load_bootstrap_object


class Command(BaseCommand):
    help = "Create or update the ACL permission catalog from a seed object."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "seed_path",
            help="Path in the form 'module.path:PERMISSION_SEEDS'.",
        )

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        seed_object = load_bootstrap_object(options["seed_path"])
        permission_seeds = self.resolve_permission_seeds(seed_object)
        bootstrapper = ACLBootstrapper()
        bootstrapper.ensure_permissions(permission_seeds)
        created = bootstrapper.summary()["permissions"]
        self.stdout.write(
            self.style.SUCCESS(
                f"ACL permission bootstrap completed. Created {created} permission rows."
            )
        )

    def resolve_permission_seeds(
        self,
        seed_object: object,
    ) -> Iterable[ACLPermissionSeed]:
        """Accept either an iterable constant or a zero-argument callable."""
        if callable(seed_object):
            seed_object = seed_object()
        if not isinstance(seed_object, Iterable):
            msg = "Permission seed object must be an iterable or zero-argument callable."
            raise CommandError(msg)
        return cast(Iterable[ACLPermissionSeed], seed_object)
