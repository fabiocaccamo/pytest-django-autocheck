"""Check: every project ModelForm can be instantiated.

A ``ModelForm`` whose ``Meta`` references a renamed or removed model field
builds its field set only when instantiated, so the mistake stays hidden until
the view that uses the form is hit. This check imports the ``forms`` module of
every project app, finds the ``ModelForm`` subclasses it defines and
instantiates each one, surfacing those errors at test time.

Forms without a concrete ``Meta.model`` (abstract base forms) are skipped, as
are forms merely imported into the module: only the model forms actually
defined by a project app are inspected. An app without a ``forms`` module is
skipped, while a ``forms`` module that exists but fails to import is reported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.forms import ModelForm

from pytest_django_autocheck.checks.shared.modules import import_optional_module
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
        for app_config in project_apps(app_configs):
            findings.extend(self._check_module(f"{app_config.name}.forms"))
        return findings

    def _check_module(self, module_name: str) -> list[Finding]:
        try:
            module = import_optional_module(module_name)
        except Exception as error:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    module_name,
                    f"could not import the module: {type(error).__name__}: {error}",
                    error,
                )
            ]
        if module is None:
            return []
        findings: list[Finding] = []
        for form_class in self._collect_forms(module):
            findings.extend(self._check_form(form_class))
        return findings

    def _check_form(self, form_class: type[ModelForm]) -> list[Finding]:
        target = f"{form_class.__module__}.{form_class.__qualname__}"
        try:
            form_class()
        except Exception as error:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"could not instantiate the form: {error}",
                    error,
                )
            ]
        return []

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
