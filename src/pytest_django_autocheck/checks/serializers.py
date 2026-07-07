"""Check: every project DRF serializer can build its fields.

A serializer whose ``Meta.fields`` references a renamed or removed model field
fails only when its ``fields`` are built, typically on the first request. This
check imports the ``serializers`` module of every project app (``<app>.
serializers`` and ``<app>.api.serializers``), finds the serializer classes it
defines and forces each one to build its fields, surfacing those errors at test
time.

The check is a no-op when Django REST Framework is not installed. Abstract base
serializers (no ``Meta.model`` and no declared fields) and serializers merely
imported into the module are skipped.
"""

import importlib
from typing import TYPE_CHECKING

from pytest_django_autocheck.checks.shared.scope import project_apps
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from types import ModuleType

    from django.apps.config import AppConfig


class SerializersCheck(BaseCheck):
    name = "serializers"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        base = self._serializer_base()
        if base is None:
            return []
        findings: list[Finding] = []
        for serializer_class in self._iter_serializers(app_configs, base):
            findings.extend(self._check_serializer(serializer_class))
        return findings

    def _check_serializer(self, serializer_class: type) -> list[Finding]:
        target = f"{serializer_class.__module__}.{serializer_class.__qualname__}"
        try:
            serializer_class().fields  # noqa: B018 - builds the field set
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"could not build the serializer fields: {exc}",
                    exc,
                )
            ]
        return []

    def _iter_serializers(
        self, app_configs: Sequence[AppConfig] | None, base: type
    ) -> Iterator[type]:
        for app_config in project_apps(app_configs):
            for module_name in (
                f"{app_config.name}.serializers",
                f"{app_config.name}.api.serializers",
            ):
                module = self._import_optional(module_name)
                if module is None:
                    continue
                yield from self._collect_serializers(module, base)

    @staticmethod
    def _serializer_base() -> type | None:
        try:
            module = importlib.import_module("rest_framework.serializers")
        except ImportError:
            return None
        return module.Serializer

    @staticmethod
    def _import_optional(name: str) -> ModuleType | None:
        try:
            return importlib.import_module(name)
        except ImportError:
            return None

    @staticmethod
    def _collect_serializers(module: ModuleType, base: type) -> Iterator[type]:
        for obj in vars(module).values():
            if not (
                isinstance(obj, type) and issubclass(obj, base) and obj is not base
            ):
                continue
            if obj.__module__ != module.__name__:
                continue
            meta_model = getattr(getattr(obj, "Meta", None), "model", None)
            declared = getattr(obj, "_declared_fields", {})
            if meta_model is None and not declared:
                continue
            yield obj
