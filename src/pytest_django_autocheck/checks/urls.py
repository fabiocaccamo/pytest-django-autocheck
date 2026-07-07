"""Check: the URL configuration resolves and reverses cleanly.

The root URLconf is walked recursively. Loading an included URLconf forces the
import of the module (surfacing ``ImportError``/``ImproperlyConfigured`` hidden
behind ``include()``), and every pattern's view callback is resolved (surfacing
a misspelled dotted path behind a string view). For every named pattern a
best-effort ``reverse()`` is attempted: a ``NoReverseMatch`` is ignored because
it usually means the URL legitimately requires arguments, while any other
exception is reported.

The check makes no assumption about the project: it starts from
``get_resolver()`` (the active ``ROOT_URLCONF``) and tracks namespaces so the
reverse lookups use the fully qualified names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import NoReverseMatch, get_resolver, reverse
from django.urls.resolvers import URLResolver

from pytest_django_autocheck.registry import BaseCheck, Finding

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps.config import AppConfig


class UrlsCheck(BaseCheck):
    name = "urls"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        return self._walk(get_resolver())

    def _walk(self, resolver: URLResolver, namespace_prefix: str = "") -> list[Finding]:
        try:
            patterns = resolver.url_patterns
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            target = str(getattr(resolver, "urlconf_name", resolver))
            return [
                Finding(
                    self.name,
                    "ERROR",
                    target,
                    f"could not load the included URLconf: {exc}",
                    exc,
                )
            ]

        findings: list[Finding] = []
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                namespace = pattern.namespace
                child_prefix = (
                    f"{namespace_prefix}{namespace}:" if namespace else namespace_prefix
                )
                findings.extend(self._walk(pattern, child_prefix))
            else:
                findings.extend(self._check_pattern(pattern, namespace_prefix))
        return findings

    def _check_pattern(self, pattern: object, namespace_prefix: str) -> list[Finding]:
        try:
            pattern.callback  # noqa: B018 - resolves string views eagerly
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    str(pattern.pattern),
                    f"could not resolve the view: {exc}",
                    exc,
                )
            ]
        if pattern.name:
            return self._check_reverse(f"{namespace_prefix}{pattern.name}")
        return []

    def _check_reverse(self, name: str) -> list[Finding]:
        try:
            reverse(name)
        except NoReverseMatch:
            return []
        except Exception as exc:  # noqa: BLE001 - reported as a finding
            return [
                Finding(
                    self.name,
                    "ERROR",
                    name,
                    f"reverse('{name}') raised {type(exc).__name__}: {exc}",
                    exc,
                )
            ]
        return []
