"""Shared detection of project apps versus third-party/contrib apps.

An app is considered part of the project when its filesystem location does not
live under the interpreter's ``site-packages``, the standard library or the
environment prefix, and is not this package itself (even when vendored). The
detection is generic and makes no assumption about the project layout: it
relies only on each ``AppConfig`` filesystem ``path``.

Both the imports check (which modules to import eagerly) and the migrations
probe (which apps to reverse on the throwaway database) rely on this logic, so
it lives in a single place to stay consistent.
"""

from __future__ import annotations

import functools
import os
import re
import site
import sysconfig
from typing import TYPE_CHECKING

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from pytest_django_autocheck.settings import get_setting

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig
    from django.db.models import Model

_TESTS_MODULE_RE = re.compile(r"(^|\.)tests(\.|$)")


@functools.lru_cache(maxsize=1)
def own_package_dir() -> str:
    """Return this package's directory, used to exclude its own modules."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


@functools.lru_cache(maxsize=1)
def external_prefixes() -> tuple[str, ...]:
    """Return realpath prefixes considered external (pip/stdlib/env)."""
    paths = sysconfig.get_paths()
    candidates = [
        *site.getsitepackages(),
        site.getusersitepackages(),
        paths["purelib"],
        paths["platlib"],
        paths["stdlib"],
        paths["platstdlib"],
    ]
    return tuple(sorted({os.path.realpath(path) for path in candidates}))


def is_within(real_path: str, parent: str) -> bool:
    """Return ``True`` when ``real_path`` is ``parent`` or nested under it."""
    return real_path == parent or real_path.startswith(parent + os.sep)


def excluded_model_labels() -> set[str]:
    """Return the lowercased labels from the ``MODELS_EXCLUDE`` setting."""
    value = get_setting("MODELS_EXCLUDE")
    if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
        raise ImproperlyConfigured(
            "PYTEST_DJANGO_AUTOCHECK_MODELS_EXCLUDE must be a list of "
            f"'app_label.ModelName' labels, got {value!r}."
        )
    labels = {label.lower() for label in value}
    _validate_model_labels(labels, "PYTEST_DJANGO_AUTOCHECK_MODELS_EXCLUDE")
    return labels


def model_factory_paths() -> dict[str, str]:
    """Return lowercased label -> dotted path from ``MODELS_FACTORIES``."""
    value = get_setting("MODELS_FACTORIES")
    if not isinstance(value, dict):
        raise ImproperlyConfigured(
            "PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES must be a dict mapping "
            f"'app_label.ModelName' labels to dotted paths, got {value!r}."
        )
    paths = {label.lower(): path for label, path in value.items()}
    _validate_model_labels(set(paths), "PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES")
    return paths


def _validate_model_labels(labels: set[str], setting_name: str) -> None:
    """Fail loudly on labels that match no installed model.

    A silently ignored typo would exclude nothing (or configure a factory for
    nothing) while the developer believes it did.
    """
    installed = {model._meta.label_lower for model in apps.get_models()}
    unknown = sorted(labels - installed)
    if unknown:
        raise ImproperlyConfigured(
            f"{setting_name} references unknown model label(s): "
            f"{', '.join(unknown)}."
        )


def is_test_support_model(model: type[Model]) -> bool:
    """Return ``True`` when ``model`` is defined in a ``tests`` module.

    Models declared inside a ``tests`` package (a top-level ``tests/`` or an
    app-level ``{app}/tests/``) only support the project's own test suite, so
    the checks skip them. The app's own dotted path is stripped before
    matching: an app deliberately installed from within a tests package (such
    as this plugin's own fixture app) is still inspected.
    """
    module = model.__module__
    app_name = model._meta.app_config.name
    if module == app_name or module.startswith(app_name + "."):
        module = module[len(app_name) + 1 :]
    return _TESTS_MODULE_RE.search(module) is not None


def is_project_app(app_config: AppConfig) -> bool:
    """Return ``True`` when the app belongs to the project under inspection."""
    path = app_config.path
    if not path:
        return False
    real_path = os.path.realpath(path)
    if is_within(real_path, own_package_dir()):
        return False
    return not any(is_within(real_path, prefix) for prefix in external_prefixes())


def project_app_configs() -> Iterator[AppConfig]:
    """Yield the ``AppConfig`` of every project app."""
    for app_config in apps.get_app_configs():
        if is_project_app(app_config):
            yield app_config


def project_apps(
    app_configs: Sequence[AppConfig] | None,
) -> list[AppConfig]:
    """Return the project apps among ``app_configs``.

    ``None`` means "every project app"; an explicit sequence is filtered so
    third-party and ``django.contrib`` apps are never inspected.
    """
    if app_configs is None:
        return list(project_app_configs())
    return [config for config in app_configs if is_project_app(config)]


def project_app_labels() -> set[str]:
    """Return the set of labels of every project app."""
    return {app_config.label for app_config in project_app_configs()}


def inspected_labels(
    app_configs: Sequence[AppConfig] | None,
) -> set[str]:
    """Return the labels to inspect, defaulting to the project's own apps.

    ``None`` does **not** mean "no restriction": it means "every project app".
    Checks that must never inspect third-party or ``django.contrib`` apps
    (models, admin, migrations) use this so a broken dependency the project
    does not own cannot fail its build.
    """
    if app_configs is None:
        return project_app_labels()
    return {app_config.label for app_config in app_configs}
