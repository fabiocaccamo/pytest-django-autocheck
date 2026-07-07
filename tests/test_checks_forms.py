"""Tests for the forms check."""

import types

from django import forms
from django.apps import apps

from pytest_django_autocheck.checks import forms as forms_module
from pytest_django_autocheck.checks.forms import FormsCheck
from tests.exampleapp.forms import AuthorForm
from tests.exampleapp.models import Author


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = FormsCheck()
    assert check.name == "forms"
    assert check.severity == "ERROR"


def test_clean_project_has_no_findings() -> None:
    check = FormsCheck()
    assert check.run(None) == []


def test_explicit_app_configs_are_inspected() -> None:
    check = FormsCheck()
    assert check.run(_exampleapp()) == []


def test_project_form_is_discovered() -> None:
    check = FormsCheck()
    assert AuthorForm in set(check._iter_forms(None))


def test_collect_forms_skips_abstract_and_imported(monkeypatch) -> None:
    module = types.ModuleType("fake_forms")

    class Good(forms.ModelForm):
        class Meta:
            model = Author
            fields = ["name"]

    class Abstract(forms.ModelForm):
        pass

    Good.__module__ = "fake_forms"
    Abstract.__module__ = "fake_forms"
    module.Good = Good
    module.Abstract = Abstract
    module.Imported = AuthorForm
    module.not_a_form = object()

    collected = list(FormsCheck._collect_forms(module))
    assert collected == [Good]


def test_import_forms_returns_none_when_absent() -> None:
    assert FormsCheck._import_forms("nonexistent_package_xyz") is None


def test_iter_forms_skips_apps_without_forms(monkeypatch) -> None:
    class FakeConfig:
        name = "nonexistent_package_xyz"

    monkeypatch.setattr(
        forms_module, "project_apps", lambda app_configs: [FakeConfig()]
    )
    check = FormsCheck()
    assert list(check._iter_forms(None)) == []


def test_instantiation_failure_is_reported() -> None:
    class BoomForm:
        __qualname__ = "BoomForm"
        __module__ = "tests.fake"

        def __init__(self) -> None:
            raise ValueError("unknown field 'ghost'")

    check = FormsCheck()
    findings = check._check_form(BoomForm)
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "tests.fake.BoomForm"
    assert "unknown field" in findings[0].message
