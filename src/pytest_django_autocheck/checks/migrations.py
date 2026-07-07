"""Check: migrations are reversible, complete and applicable.

For every migration of a *project* app on disk (squash ``replaces`` excluded)
the operations are inspected for reversibility. ``RunPython``/``RunSQL``
operations without an explicit reverse raise ``IrreversibleError`` when rolled
back and are reported as ``ERROR``; the same operations using an explicit no-op
reverse (``RunPython.noop`` / ``RunSQL.noop``) are reported separately as
``WARNING`` because they reverse silently but may drop data. Third-party and
``django.contrib`` migrations are skipped: some legitimately ship irreversible
data migrations the project does not own, so flagging them would be noise.

The check also detects *missing* migrations: when a project app has model
changes that are not captured by any migration on disk (the equivalent of
``makemigrations --check``), it is reported as ``ERROR`` because the schema
would drift on deploy. This static comparison is restricted to project apps so
third-party apps never produce noise.

The static inspections above rely only on the migration loader and never touch
a database. In addition, the check verifies migrations dynamically: it spawns a
short-lived subprocess that creates a throwaway database (isolated from the
suite's own test database), then applies every migration forward, reverses it
to zero and re-applies it forward again. Any failure in that cycle is reported
as ``ERROR``; if the environment cannot be set up, the dynamic step is skipped
with a ``WARNING`` and never breaks the suite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations import RunPython, RunSQL
from django.db.migrations.state import ProjectState

from pytest_django_autocheck.checks.probe import (
    EXIT_OK,
    EXIT_SETUP_ERROR,
    PROBE_DEADLINE_ENV,
)
from pytest_django_autocheck.checks.shared.scope import inspected_labels
from pytest_django_autocheck.registry import BaseCheck, Finding
from pytest_django_autocheck.settings import get_setting

# Extra seconds the parent waits beyond the probe's own deadline, so the probe
# can self-abort and destroy its throwaway database before the parent has to
# kill it (which would leak the database).
_PROBE_TIMEOUT_BUFFER = 30

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig
    from django.db.migrations.migration import Migration
    from django.db.migrations.operations.base import Operation


class MigrationsCheck(BaseCheck):
    name = "migrations"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        loader = MigrationLoader(None, ignore_no_migrations=True)
        replaced = self._replaced_keys(loader.replacements)
        allowed = inspected_labels(app_configs)

        findings: list[Finding] = []
        for key, migration in self._iter_targets(
            loader.disk_migrations, replaced, allowed
        ):
            app_label, name = key
            target = f"{app_label}.{name}"
            findings.extend(self._inspect(migration.operations, target))

        findings.extend(self._detect_missing(loader, allowed))
        findings.extend(self._inspect_database())
        return findings

    def _detect_missing(
        self, loader: MigrationLoader, allowed: set[str]
    ) -> list[Finding]:
        autodetector = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
        )
        changes = autodetector.changes(graph=loader.graph)
        return [
            self._missing_finding(app_label, migrations)
            for app_label, migrations in sorted(changes.items())
            if app_label in allowed
        ]

    def _missing_finding(
        self, app_label: str, migrations: Sequence[Migration]
    ) -> Finding:
        operations = [
            type(operation).__name__
            for migration in migrations
            for operation in migration.operations
        ]
        summary = ", ".join(operations)
        return Finding(
            self.name,
            "ERROR",
            app_label,
            "model changes are not captured by a migration; run "
            f"'makemigrations {app_label}' ({summary}).",
        )

    _PROBE_MODULE = "pytest_django_autocheck.checks.probe"

    def _inspect_database(self) -> list[Finding]:
        env = self._subprocess_env()
        if env is None:
            return [
                Finding(
                    self.name,
                    "WARNING",
                    "database",
                    "Django settings are configured without a settings module "
                    "(settings.configure()), so the dynamic migration check "
                    "cannot run in a subprocess; skipping.",
                )
            ]
        timeout = get_setting("MIGRATIONS_PROBE_TIMEOUT")
        env[PROBE_DEADLINE_ENV] = str(timeout)
        try:
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-m", self._PROBE_MODULE],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=timeout + _PROBE_TIMEOUT_BUFFER,
            )
        except subprocess.TimeoutExpired as exc:
            return [
                Finding(
                    self.name,
                    "WARNING",
                    "database",
                    "the migration probe timed out, skipping "
                    f"({exc.timeout:g}s); set "
                    "PYTEST_DJANGO_AUTOCHECK_MIGRATIONS_PROBE_TIMEOUT to "
                    "raise the limit.",
                    exc,
                )
            ]
        except OSError as exc:
            return [
                Finding(
                    self.name,
                    "WARNING",
                    "database",
                    "could not launch the migration probe, skipping " f"({exc}).",
                    exc,
                )
            ]

        if result.returncode == EXIT_OK:
            return []

        message = (result.stderr or result.stdout or "").strip()
        if result.returncode == EXIT_SETUP_ERROR:
            return [
                Finding(
                    self.name,
                    "WARNING",
                    "database",
                    "could not verify migrations dynamically, skipping "
                    f"({message}).",
                )
            ]
        return [
            Finding(
                self.name,
                "ERROR",
                "database",
                "migrations could not be applied forward, reversed to zero "
                f"and re-applied on a temporary database ({message}).",
            )
        ]

    @staticmethod
    def _subprocess_env() -> dict[str, str] | None:
        """Build the environment for the probe subprocess.

        The probe runs a fresh interpreter, so it must be told which settings
        module to load and where to import the project from. Both are derived
        from the running process (``settings.SETTINGS_MODULE`` and
        ``sys.path``) rather than relying on inherited environment variables,
        which are absent when settings come from ``pytest.ini``/``--ds`` or
        when the project uses a ``src`` layout. Returns ``None`` when settings
        were configured without a module, which the subprocess cannot import.
        """
        settings_module = settings.SETTINGS_MODULE
        if not settings_module:
            return None
        env = dict(os.environ)
        env["DJANGO_SETTINGS_MODULE"] = settings_module
        search_path = [entry for entry in sys.path if entry]
        existing = env.get("PYTHONPATH")
        if existing:
            search_path.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(search_path)
        return env

    @staticmethod
    def _replaced_keys(
        replacements: dict[tuple[str, str], object],
    ) -> set[tuple[str, str]]:
        replaced: set[tuple[str, str]] = set()
        for migration in replacements.values():
            replaced.update(migration.replaces)
        return replaced

    @staticmethod
    def _iter_targets(
        disk_migrations: dict[tuple[str, str], object],
        replaced: set[tuple[str, str]],
        allowed: set[str],
    ) -> Iterator[tuple[tuple[str, str], object]]:
        for key, migration in sorted(disk_migrations.items()):
            app_label, _name = key
            if key in replaced or app_label not in allowed:
                continue
            yield key, migration

    def _inspect(self, operations: Sequence[Operation], target: str) -> list[Finding]:
        findings: list[Finding] = []
        for operation in operations:
            if isinstance(operation, RunPython):
                findings.extend(
                    self._inspect_reverse(
                        target,
                        is_irreversible=operation.reverse_code is None,
                        is_noop=operation.reverse_code is RunPython.noop,
                        label="RunPython",
                    )
                )
            elif isinstance(operation, RunSQL):
                findings.extend(
                    self._inspect_reverse(
                        target,
                        is_irreversible=operation.reverse_sql is None,
                        is_noop=operation.reverse_sql == RunSQL.noop,
                        label="RunSQL",
                    )
                )
        return findings

    def _inspect_reverse(
        self,
        target: str,
        *,
        is_irreversible: bool,
        is_noop: bool,
        label: str,
    ) -> list[Finding]:
        if is_irreversible:
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"{label} operation is irreversible "
                    "(no reverse_code/reverse_sql).",
                )
            ]
        if is_noop:
            return [
                Finding(
                    self.name,
                    "WARNING",
                    target,
                    f"{label} operation reverses to a no-op: it is technically "
                    "reversible but may silently drop data.",
                )
            ]
        return []
