from __future__ import annotations

from typing import Any, cast

from django.core.management.base import BaseCommand, CommandError

from ...acl_bootstrap import ACLBootstrapper, load_bootstrap_object


class Command(BaseCommand):
    help = "Run one project-defined ACL bootstrap callable."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "bootstrap_path",
            help="Path in the form 'module.path:bootstrap_callable'.",
        )

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        bootstrap_object = load_bootstrap_object(options["bootstrap_path"])
        if not callable(bootstrap_object):
            msg = "Bootstrap object must be callable and accept one ACLBootstrapper."
            raise CommandError(msg)
        bootstrapper = ACLBootstrapper()
        callable_object = cast(Any, bootstrap_object)
        bootstrap_result = callable_object(bootstrapper)
        summary = bootstrapper.summary()
        summary_text = ", ".join(
            f"{key}={value}" for key, value in summary.items()
        )
        extra_text = f" Result: {bootstrap_result}" if bootstrap_result else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"ACL bootstrap completed ({summary_text}).{extra_text}"
            )
        )
