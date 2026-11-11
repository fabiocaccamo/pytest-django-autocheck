"""Tests for the shared URLconf helpers."""

import types

from pytest_django_autocheck.checks.shared.urls import nested_namespace_prefix


def _resolver(namespace: str | None) -> types.SimpleNamespace:
    return types.SimpleNamespace(namespace=namespace)


def test_namespace_is_appended_to_an_empty_prefix() -> None:
    assert nested_namespace_prefix("", _resolver("shop")) == "shop:"


def test_namespaces_are_chained() -> None:
    assert nested_namespace_prefix("shop:", _resolver("api")) == "shop:api:"


def test_resolver_without_namespace_keeps_the_prefix() -> None:
    assert nested_namespace_prefix("shop:", _resolver(None)) == "shop:"
    assert nested_namespace_prefix("", _resolver(None)) == ""
