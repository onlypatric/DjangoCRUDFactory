from __future__ import annotations

from argparse import ArgumentParser

from django.core.management.base import BaseCommand

from tests.production_app.demo_seed import seed_demo_locations


class Command(BaseCommand):
    help = "Populate the production_app EV models with reusable demo data."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing EV demo rows before seeding fresh data.",
        )

    def handle(self, *args: object, **options: object) -> str:
        replace = bool(options.get("replace", False))
        counts = seed_demo_locations(replace=replace)
        message = (
            "Seeded EV demo data: "
            f"{counts['locations']} locations, "
            f"{counts['chargepoints']} chargepoints, "
            f"{counts['connectors']} connectors created."
        )
        self.stdout.write(self.style.SUCCESS(message))
        return message
