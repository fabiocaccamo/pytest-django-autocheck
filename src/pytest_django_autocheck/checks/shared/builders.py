"""Generic instance generation shared by the models and admin checks.

The admin change-view check reuses the same mechanism used by the models check
to obtain a valid, saved instance for any model.

Generation strategy, in order of priority:

1. if the project ships ``factory_boy`` factories (``<app>.factories`` or
   ``<app>.tests.factories``), use the matching factory: it already encodes the
   project's domain rules, so it avoids the false positives that random data
   would trigger on ``clean()``/validators/constraints;
2. otherwise fall back to ``model_bakery.baker.make()``, which resolves
   required fields and foreign keys recursively.

The discovery stays fully generic: it relies on ``INSTALLED_APPS`` and standard
import, never on a fixed folder layout, and is a no-op when ``factory_boy`` is
not installed in the project.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import TYPE_CHECKING

from django.apps import apps

if TYPE_CHECKING:
    from types import ModuleType

    from django.db.models import Model


def make_instance(model: type[Model]) -> Model:
    """Create and persist a valid instance of ``model``.

    Uses a project factory when one is found, otherwise ``model_bakery``.
    Raises whatever exception generation triggers; callers are expected to
    wrap it into a :class:`~pytest_django_autocheck.registry.Finding`.
    """
    factory_class = _factory_for(model)
    if factory_class is not None:
        return factory_class.create()

    from model_bakery import baker

    return baker.make(model)


def _factory_for(model: type[Model]) -> type | None:
    return _discover_factories().get(model)


@lru_cache(maxsize=1)
def _discover_factories() -> dict[type[Model], type]:
    """Map each model to the first project factory that builds it."""
    base = _factory_base()
    if base is None:
        return {}

    mapping: dict[type[Model], type] = {}
    for app_config in apps.get_app_configs():
        for module_name in (
            f"{app_config.name}.factories",
            f"{app_config.name}.tests.factories",
        ):
            module = _import_optional(module_name)
            if module is None:
                continue
            _collect_factories(module, base, mapping)
    return mapping


def _factory_base() -> type | None:
    try:
        from factory.django import DjangoModelFactory
    except ImportError:
        return None
    return DjangoModelFactory


def _import_optional(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _collect_factories(
    module: ModuleType,
    base: type,
    mapping: dict[type[Model], type],
) -> None:
    for obj in vars(module).values():
        if not (isinstance(obj, type) and issubclass(obj, base) and obj is not base):
            continue
        model = getattr(getattr(obj, "_meta", None), "model", None)
        if model is not None and model not in mapping:
            mapping[model] = obj
