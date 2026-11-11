"""Shared URLconf helpers for the checks that walk the URL resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.urls.resolvers import URLResolver


def nested_namespace_prefix(namespace_prefix: str, resolver: URLResolver) -> str:
    """Return the prefix qualifying the names declared under ``resolver``.

    ``reverse()`` needs the chain of namespaces (``"shop:api:"``) in front of
    a pattern name; a resolver without a namespace leaves the prefix as is.
    """
    namespace = resolver.namespace
    return f"{namespace_prefix}{namespace}:" if namespace else namespace_prefix
