"""Check: every project ModelForm can be instantiated.

A ``ModelForm`` whose ``Meta`` references a renamed or removed model field
builds its field set only when instantiated, so the mistake stays hidden until
the view that uses the form is hit. This check imports the ``forms`` module of
every project app, finds the ``ModelForm`` subclasses it defines and
instantiates each one, surfacing those errors at test time.

Forms without a concrete ``Meta.model`` (abstract base forms) are skipped, as
are forms merely imported into the module: only the model forms actually
defined by a project app are inspected.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from django.forms import ModelForm

from pytest_django_autocheck.checks.shared.scope import project_apps
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from types import ModuleType

    from django.apps.config import AppConfig


class FormsCheck(BaseCheck):
    name = "forms"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        findings: list[Finding] = []
        for form_class in self._iter_forms(app_configs):
            findings.extend(self._check_form(form_class))
        return findings

    def _check_form(self, form_class: type[ModelForm]) -> list[Finding]:
        target = f"{form_class.__module__}.{form_class.__qualname__}"
        try:
            form_class()
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"could not instantiate the form: {exc}",
                    exc,
                )
            ]
        return []

    def _iter_forms(
        self, app_configs: Sequence[AppConfig] | None
    ) -> Iterator[type[ModelForm]]:
        for app_config in project_apps(app_configs):
            module = self._import_forms(app_config.name)
            if module is None:
                continue
            yield from self._collect_forms(module)

    @staticmethod
    def _import_forms(app_name: str) -> ModuleType | None:
        try:
            return importlib.import_module(f"{app_name}.forms")
        except ImportError:
            return None

    @staticmethod
    def _collect_forms(module: ModuleType) -> Iterator[type[ModelForm]]:
        for obj in vars(module).values():
            if not (
                isinstance(obj, type)
                and issubclass(obj, ModelForm)
                and obj is not ModelForm
            ):
                continue
            if obj.__module__ != module.__name__:
                continue
            meta = getattr(obj, "_meta", None)
            if meta is None or getattr(meta, "model", None) is None:
                continue
            yield obj
