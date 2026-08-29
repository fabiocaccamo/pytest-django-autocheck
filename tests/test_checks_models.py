"""Tests for the models check (PoC 4.2)."""

import pytest
from django.apps import apps

from pytest_django_autocheck.checks import models as models_module
from pytest_django_autocheck.checks.models import ModelsCheck
from tests.exampleapp.models import Author, AuthorProxy, UnmanagedThing

pytestmark = pytest.mark.django_db


def _exampleapp():
    return [apps.get_app_config("exampleapp")]


def test_check_metadata() -> None:
    check = ModelsCheck()
    assert check.name == "models"
    assert check.severity == "ERROR"


def test_clean_models_have_no_findings() -> None:
    check = ModelsCheck()
    assert check.run(_exampleapp()) == []


def test_run_on_whole_project_has_no_errors() -> None:
    check = ModelsCheck()
    findings = check.run(None)
    assert [f for f in findings if f.severity == "ERROR"] == []


def test_proxy_and_unmanaged_models_are_skipped() -> None:
    inspected = {model.__name__ for model in ModelsCheck._iter_models(_exampleapp())}
    assert "Author" in inspected
    assert AuthorProxy.__name__ not in inspected
    assert UnmanagedThing.__name__ not in inspected


def test_test_support_models_are_skipped(monkeypatch) -> None:
    monkeypatch.setattr(Author, "__module__", "tests.exampleapp.tests.models")
    inspected = {model.__name__ for model in ModelsCheck._iter_models(_exampleapp())}
    assert "Author" not in inspected


def test_iter_models_excludes_third_party_apps() -> None:
    labels = {model._meta.app_label for model in ModelsCheck._iter_models(None)}
    assert "exampleapp" in labels
    assert "auth" not in labels
    assert "contenttypes" not in labels


def test_instance_creation_failure_is_reported(monkeypatch) -> None:
    def boom(model):
        raise ValueError("cannot build")

    monkeypatch.setattr(models_module, "make_instance", boom)
    check = ModelsCheck()
    findings = check.run(_exampleapp())
    assert findings
    assert all(f.severity == "ERROR" for f in findings)
    assert "cannot build" in findings[0].message


def test_instance_creation_failure_rolls_back_partial_writes(
    monkeypatch,
) -> None:
    """A failing generation must not leak writes nor poison the transaction.

    Each model runs in its own savepoint: on PostgreSQL a failed query aborts
    the whole transaction, so without the savepoint the first broken model
    would cascade errors onto every model checked after it.
    """

    def partial_write_then_boom(model):
        Author.objects.create(name="leaked")
        raise ValueError("boom after write")

    monkeypatch.setattr(models_module, "make_instance", partial_write_then_boom)
    check = ModelsCheck()
    findings = check.run(_exampleapp())
    assert findings
    assert Author.objects.count() == 0
    assert Author.objects.filter(name="leaked").exists() is False


def test_str_failure_is_reported(monkeypatch) -> None:
    class Boom:
        def __str__(self) -> str:
            raise RuntimeError("bad str")

    monkeypatch.setattr(models_module, "make_instance", lambda model: Boom())
    check = ModelsCheck()
    findings = check.run(_exampleapp())
    assert findings
    assert all(f.severity == "ERROR" for f in findings)
    assert "bad str" in findings[0].message


def test_repr_failure_is_reported(monkeypatch) -> None:
    class Boom:
        def __repr__(self) -> str:
            raise RuntimeError("bad repr")

    monkeypatch.setattr(models_module, "make_instance", lambda model: Boom())
    check = ModelsCheck()
    findings = check.run(_exampleapp())
    assert findings
    assert all(f.severity == "ERROR" for f in findings)
    assert any("bad repr" in f.message for f in findings)
