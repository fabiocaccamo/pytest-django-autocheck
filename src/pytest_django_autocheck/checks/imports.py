"""Check: every module of every project app is importable.

Production code often imports modules lazily (inside functions, management
commands, signal handlers, Celery tasks), so an ``ImportError`` or a circular
import can stay dormant until the exact code path runs in production. This
check imports every Python module of every *project* app eagerly, surfacing
those failures at test time.

Third-party apps installed through pip are skipped: an app is considered
external when its filesystem location lives under the interpreter's
``site-packages``, the standard library or the environment prefix. The
detection is generic, with no assumption about the project layout, and relies
on each ``AppConfig`` to provide both the dotted package name
(``app_config.name``) and the filesystem location (``app_config.path``).
``migrations`` packages, ``__pycache__`` and dunder modules are skipped, and
circular imports are reported with a dedicated message.

This package itself is always excluded, even when it is vendored (copied into
the project instead of installed via pip): its own directory is detected by
path and pruned from the walk, so the check never imports its own modules.
"""

import importlib
import os
from typing import TYPE_CHECKING

from django.apps import apps

from pytest_django_autocheck.checks.shared.scope import (
    is_project_app,
    own_package_dir,
)
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig

_SKIP_DIRS = {"__pycache__", "migrations"}


class ImportsCheck(BaseCheck):
    name = "imports"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        findings: list[Finding] = []
        for module_path in self._iter_modules(app_configs):
            findings.extend(self._check_module(module_path))
        return findings

    def _check_module(self, module_path: str) -> list[Finding]:
        try:
            importlib.import_module(module_path)
        except ImportError as exc:
            message = (
                f"circular import: {exc}"
                if self._is_circular_import(exc)
                else f"ImportError: {exc}"
            )
            return [Finding(self.name, "ERROR", module_path, message, exc)]
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    module_path,
                    f"import raised {type(exc).__name__}: {exc}",
                    exc,
                )
            ]
        return []

    @staticmethod
    def _is_circular_import(exc: ImportError) -> bool:
        message = str(exc)
        return "circular import" in message or "partially initialized module" in message

    @staticmethod
    def _iter_modules(
        app_configs: Sequence[AppConfig] | None,
    ) -> Iterator[str]:
        configs = apps.get_app_configs() if app_configs is None else app_configs
        for app_config in configs:
            if not is_project_app(app_config):
                continue
            yield from ImportsCheck._iter_app_modules(app_config)

    @staticmethod
    def _iter_app_modules(app_config: AppConfig) -> Iterator[str]:
        base_path = app_config.path
        base_name = app_config.name
        own = own_package_dir()
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [
                d
                for d in dirs
                if d not in _SKIP_DIRS
                and os.path.realpath(os.path.join(root, d)) != own
            ]
            prefix = ImportsCheck._module_prefix(base_name, base_path, root)
            for file in files:
                if not file.endswith(".py") or file.startswith("__"):
                    continue
                name = file[:-3]
                yield f"{prefix}.{name}" if prefix else name

    @staticmethod
    def _module_prefix(base_name: str, base_path: str, root: str) -> str:
        relative = os.path.relpath(root, base_path)
        if relative == ".":
            return base_name
        suffix = relative.replace(os.sep, ".")
        return f"{base_name}.{suffix}"
