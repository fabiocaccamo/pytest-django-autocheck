"""Check: every project management command imports and builds its parser.

Management commands are imported lazily by ``manage.py``, so an ``ImportError``
in a command module (or a broken ``add_arguments``) stays dormant until someone
runs that command, typically in a cron job or a deploy script. This check
loads every command shipped by a *project* app and builds its argument parser,
surfacing those failures at test time.

Commands shipped by Django itself and by third-party apps are skipped: only
commands whose owning app is a project app are inspected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management import get_commands, load_command_class

from pytest_django_autocheck.checks.shared.scope import project_apps
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps.config import AppConfig


class ManagementCommandsCheck(BaseCheck):
    name = "management_commands"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        allowed = self._allowed_app_names(app_configs)
        findings: list[Finding] = []
        for name, app_name in sorted(get_commands().items()):
            if app_name not in allowed:
                continue
            findings.extend(self._check_command(app_name, name))
        return findings

    @staticmethod
    def _allowed_app_names(
        app_configs: Sequence[AppConfig] | None,
    ) -> set[str]:
        return {config.name for config in project_apps(app_configs)}

    def _check_command(self, app_name: str, name: str) -> list[Finding]:
        try:
            command = load_command_class(app_name, name)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    name,
                    f"could not load the command: {exc}",
                    exc,
                )
            ]
        try:
            command.create_parser("manage.py", name)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    name,
                    f"create_parser raised {type(exc).__name__}: {exc}",
                    exc,
                )
            ]
        return []
