"""Check: every project template compiles.

A template syntax error (a typo in a tag, an unknown ``{% load %}``) is only
raised when the template is rendered, so it can reach production untested. This
check enumerates the template files owned by the project (the explicit
``DIRS`` and the ``templates`` directory of every project app) and compiles
each one through its engine, surfacing syntax errors at test time.

Only the Django template backend is inspected, and only project-owned
directories: templates shipped by Django itself or by third-party apps (under
``site-packages``) are skipped, so the check never fails on code the project
does not own.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.template import TemplateSyntaxError, engines
from django.template.backends.django import DjangoTemplates

from pytest_django_autocheck.checks.shared.scope import (
    external_prefixes,
    is_within,
    own_package_dir,
)
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig
    from django.template.engine import Engine

_SKIP_DIRS = {"__pycache__"}


class TemplatesCheck(BaseCheck):
    name = "templates"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        findings: list[Finding] = []
        for backend, name in self._iter_templates():
            findings.extend(self._check_template(backend, name))
        return findings

    def _check_template(self, backend: DjangoTemplates, name: str) -> list[Finding]:
        try:
            backend.get_template(name)
        except TemplateSyntaxError as exc:
            return [
                Finding(
                    self.name,
                    "ERROR",
                    name,
                    f"template syntax error: {exc}",
                    exc,
                )
            ]
        except UnicodeDecodeError:
            # A binary asset (favicon, compiled .mo, image) sitting in a
            # templates directory is not a template; skip it instead of
            # crashing the check on an undecodable file.
            return []
        return []

    def _iter_templates(self) -> Iterator[tuple[DjangoTemplates, str]]:
        for backend in engines.all():
            if not isinstance(backend, DjangoTemplates):
                continue
            seen: set[str] = set()
            for directory in self._project_dirs(backend.engine):
                for name in self._walk_dir(directory):
                    if name in seen:
                        continue
                    seen.add(name)
                    yield backend, name

    def _project_dirs(self, engine: Engine) -> list[str]:
        dirs: list[str] = []
        seen: set[str] = set()
        for directory in self._loader_dirs(engine.template_loaders):
            real = os.path.realpath(directory)
            if real in seen:
                continue
            seen.add(real)
            if self._is_project_dir(real):
                dirs.append(directory)
        return dirs

    def _loader_dirs(self, loaders: object) -> list[str]:
        dirs: list[str] = []
        for loader in loaders:
            inner = getattr(loader, "loaders", None)
            if inner is not None:
                dirs.extend(self._loader_dirs(inner))
                continue
            get_dirs = getattr(loader, "get_dirs", None)
            if get_dirs is not None:
                dirs.extend(os.fspath(path) for path in get_dirs())
        return dirs

    @staticmethod
    def _is_project_dir(real_dir: str) -> bool:
        if is_within(real_dir, own_package_dir()):
            return False
        return not any(is_within(real_dir, prefix) for prefix in external_prefixes())

    @staticmethod
    def _walk_dir(directory: str) -> Iterator[str]:
        for root, subdirs, files in os.walk(directory):
            subdirs[:] = [d for d in subdirs if d not in _SKIP_DIRS]
            for file in files:
                full = os.path.join(root, file)
                relative = os.path.relpath(full, directory)
                yield relative.replace(os.sep, "/")
