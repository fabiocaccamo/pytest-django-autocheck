"""Tests for the programmatic runner and the text output formatter."""

import pytest
from django.test import override_settings

from pytest_django_autocheck.output.text import format_text
from pytest_django_autocheck.registry import Finding
from pytest_django_autocheck.runner import get_checks


def test_get_checks_returns_all_by_default() -> None:
    names = {check.name for check in get_checks()}
    assert {"imports", "migrations", "models", "admin"} <= names


def test_get_checks_filters_by_name() -> None:
    checks = get_checks(only=["admin"])
    assert [check.name for check in checks] == ["admin"]


@override_settings(PYTEST_DJANGO_AUTOCHECK_CHECKS=["imports", "models"])
def test_get_checks_falls_back_to_setting() -> None:
    names = [check.name for check in get_checks()]
    assert names == ["imports", "models"]


@override_settings(PYTEST_DJANGO_AUTOCHECK_CHECKS=["imports"])
def test_explicit_only_overrides_setting() -> None:
    names = [check.name for check in get_checks(only=["admin"])]
    assert names == ["admin"]


def test_get_checks_excludes_skipped() -> None:
    names = {check.name for check in get_checks(skip=["templates", "forms"])}
    assert "templates" not in names
    assert "forms" not in names
    assert "imports" in names


def test_skip_wins_over_only() -> None:
    checks = get_checks(only=["admin", "models"], skip=["models"])
    assert [check.name for check in checks] == ["admin"]


def test_get_checks_rejects_unknown_only() -> None:
    with pytest.raises(ValueError, match="unknown autocheck only"):
        get_checks(only=["admins"])


def test_get_checks_rejects_unknown_skip() -> None:
    with pytest.raises(ValueError, match="unknown autocheck skip"):
        get_checks(skip=["nope"])


@override_settings(PYTEST_DJANGO_AUTOCHECK_CHECKS=["bogus"])
def test_get_checks_rejects_unknown_setting() -> None:
    with pytest.raises(ValueError, match="unknown autocheck only"):
        get_checks()


@override_settings(PYTEST_DJANGO_AUTOCHECK_SKIP=["templates"])
def test_get_checks_falls_back_to_skip_setting() -> None:
    names = {check.name for check in get_checks()}
    assert "templates" not in names
    assert "imports" in names


def test_format_text_empty() -> None:
    assert "no issues found" in format_text([])


def test_format_text_orders_by_severity() -> None:
    findings = [
        Finding("c", "WARNING", "b", "warn"),
        Finding("c", "ERROR", "a", "err"),
    ]
    text = format_text(findings)
    assert text.index("[ERROR]") < text.index("[WARNING]")
