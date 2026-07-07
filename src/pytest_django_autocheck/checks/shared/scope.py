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

import functools
import os
import site
import sysconfig
from typing import TYPE_CHECKING

from django.apps import apps

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig


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
