"""A no-op management command used to exercise the commands check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand

if TYPE_CHECKING:
    from argparse import ArgumentParser


class Command(BaseCommand):
    help = "No-op command used by the management_commands autocheck tests."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--times", type=int, default=1)

    def handle(self, *args: object, **options: object) -> None:
        pass
