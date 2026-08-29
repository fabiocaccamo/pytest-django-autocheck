"""Check: models are instantiable, stringifiable and savable.

For every concrete, managed model of a *project* app a valid instance is
generated (and persisted) through the shared generator, then ``str()`` and
``repr()`` are exercised. Failures are reported per model, each with the
original exception, so a single broken model does not hide the others.
Third-party and ``django.contrib`` models are skipped: they are not the
project's responsibility and random data could trip their own constraints.
Models defined inside a ``tests`` package (a top-level ``tests/`` or an
app-level ``{app}/tests/``) are skipped as well: they are support models for
the project's own test suite, not production models.

The generation is generic: it prefers the project's own ``factory_boy``
factories when present and falls back to ``model_bakery``, which resolves
required fields and foreign keys recursively, with no assumption about the
project under inspection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.db import transaction

from pytest_django_autocheck.checks.shared.builders import make_instance
from pytest_django_autocheck.checks.shared.scope import (
    inspected_labels,
    is_test_support_model,
)
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig
    from django.db.models import Model


class ModelsCheck(BaseCheck):
    name = "models"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        findings: list[Finding] = []
        for model in self._iter_models(app_configs):
            target = f"{model._meta.app_label}.{model.__name__}"
            # Each DB-touching step runs in its own savepoint: on databases
            # like PostgreSQL a failed query aborts the whole transaction, so
            # without the savepoint one broken model would cascade "you can't
            # execute queries until the end of the 'atomic' block" errors
            # onto every model checked after it.
            try:
                with transaction.atomic():
                    instance = make_instance(model)
            except Exception as exc:  # noqa: BLE001 - reported as a finding
                findings.append(
                    Finding(
                        self.name,
                        "ERROR",
                        target,
                        f"Could not create/save an instance: {exc}",
                        exc,
                    )
                )
                continue
            try:
                with transaction.atomic():
                    str(instance)
            except Exception as exc:  # noqa: BLE001 - reported as a finding
                findings.append(
                    Finding(
                        self.name,
                        "ERROR",
                        target,
                        f"str() raised an exception: {exc}",
                        exc,
                    )
                )
            try:
                with transaction.atomic():
                    repr(instance)
            except Exception as exc:  # noqa: BLE001 - reported as a finding
                findings.append(
                    Finding(
                        self.name,
                        "ERROR",
                        target,
                        f"repr() raised an exception: {exc}",
                        exc,
                    )
                )
        return findings

    @staticmethod
    def _iter_models(
        app_configs: Sequence[AppConfig] | None,
    ) -> Iterator[type[Model]]:
        allowed = inspected_labels(app_configs)
        for model in apps.get_models():
            opts = model._meta
            if opts.proxy or not opts.managed or opts.swapped:
                continue
            if opts.app_label not in allowed:
                continue
            if is_test_support_model(model):
                continue
            yield model
