"""Check: every public parameterless *project* URL responds without a server error.

Every named URL that reverses without arguments and whose view is owned by the
project is requested with ``GET`` by an unauthenticated test client. Only
server errors are reported: a raised exception or an HTTP 5xx response reveals
a broken view. Everything below 500 is ignored, including 404: for an anonymous
client a 404 is often legitimate (gated resources, feature flags, flatpages)
and reporting it would produce more false positives than real findings.

Although the URLconf is global and cannot be scoped per app, each pattern's
view callback can: the callback's module file is resolved and views living
under ``site-packages`` (third-party) or in this package itself are skipped,
consistent with the models/admin/migrations checks, so a dependency's broken
view never fails the project's build. Class-based views are resolved through
``view_class`` and decorated views are unwrapped first; when the module cannot
be determined the view is conservatively checked.

The ``admin`` namespace is skipped: the admin check already exercises those
views with a logged-in superuser, which is the only meaningful way to request
them. Reverse failures and broken callbacks are also ignored here because the
urls check owns them.

Like the urls check, this one starts from ``get_resolver()`` (the active
``ROOT_URLCONF``); the ``app_configs`` argument is accepted for interface
compatibility and ignored.
"""

import inspect
import os
from typing import TYPE_CHECKING

from django.db import transaction
from django.test import Client
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLResolver

from pytest_django_autocheck.checks.shared.scope import (
    external_prefixes,
    is_within,
    own_package_dir,
)
from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from django.apps.config import AppConfig

_ADMIN_NAMESPACE = "admin"


class ViewsCheck(BaseCheck):
    name = "views"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        client = Client()
        seen: set[str] = set()
        findings: list[Finding] = []
        for name in self._iter_names(get_resolver()):
            findings.extend(self._check_view(client, name, seen))
        return findings

    def _iter_names(
        self, resolver: URLResolver, namespace_prefix: str = ""
    ) -> Iterator[str]:
        try:
            patterns = resolver.url_patterns
        except Exception:  # noqa: BLE001 - the urls check reports this
            return
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                namespace = pattern.namespace
                if namespace == _ADMIN_NAMESPACE:
                    continue
                child_prefix = (
                    f"{namespace_prefix}{namespace}:" if namespace else namespace_prefix
                )
                yield from self._iter_names(pattern, child_prefix)
            elif pattern.name and self._is_project_view(pattern):
                yield f"{namespace_prefix}{pattern.name}"

    @staticmethod
    def _is_project_view(pattern: object) -> bool:
        """Return ``True`` when the pattern's view is owned by the project.

        Third-party views (under ``site-packages``/stdlib/env prefixes) and
        this package's own views are skipped so a dependency's broken view
        never fails the project's build, mirroring the scoping of the
        models/admin/migrations checks. When the module file cannot be
        determined the view is conservatively considered part of the project.
        """
        try:
            callback = pattern.callback
        except Exception:  # noqa: BLE001 - the urls check reports this
            return False
        view = inspect.unwrap(getattr(callback, "view_class", callback))
        module = inspect.getmodule(view)
        filename = getattr(module, "__file__", None)
        if filename is None:
            return True
        real = os.path.realpath(filename)
        if is_within(real, own_package_dir()):
            return False
        return not any(is_within(real, prefix) for prefix in external_prefixes())

    def _check_view(self, client: Client, name: str, seen: set[str]) -> list[Finding]:
        try:
            url = reverse(name)
        except Exception:  # noqa: BLE001 - the urls check reports this
            return []
        if url in seen:
            return []
        seen.add(url)

        try:
            # Nested savepoint: a view that dies on a broken query must not
            # poison the transaction for the URLs checked next (PostgreSQL
            # aborts the whole transaction on a failed query).
            with transaction.atomic():
                response = client.get(url)
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    name,
                    f"GET {url} raised {type(exc).__name__}: {exc}",
                    exc,
                )
            ]

        if response.status_code >= 500:
            return [
                Finding(
                    self.name,
                    "ERROR",
                    name,
                    f"GET {url} returned HTTP {response.status_code}.",
                )
            ]
        return []
