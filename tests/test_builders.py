"""Tests for the shared instance generator and factory discovery (PoC 4.2)."""

import sys

import pytest
from django.test import override_settings

from pytest_django_autocheck.checks.shared import builders
from tests.exampleapp.factories import (
    AbstractFactory,
    AuthorFactory,
    BookFactory,
)
from tests.exampleapp.models import Author, Book


def make_saved_author() -> Author:
    return Author.objects.create(name="from configured factory")


def make_unsaved_author() -> Author:
    return Author(name="unsaved")


def make_wrong_type() -> object:
    return object()


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    builders._discover_factories.cache_clear()
    yield
    builders._discover_factories.cache_clear()


def test_discovers_project_factories() -> None:
    mapping = builders._discover_factories()
    assert mapping[Author] is AuthorFactory
    assert mapping[Book] is BookFactory


def test_first_factory_wins_for_duplicate_model() -> None:
    mapping = builders._discover_factories()
    assert mapping[Author] is AuthorFactory


def test_abstract_factory_is_ignored() -> None:
    mapping = builders._discover_factories()
    assert AbstractFactory not in mapping.values()


@pytest.mark.django_db
def test_make_instance_uses_project_factory() -> None:
    instance = builders.make_instance(Author)
    assert isinstance(instance, Author)
    assert instance.pk is not None
    assert instance.name.startswith("Author ")


@pytest.mark.django_db
@override_settings(
    PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES={
        "ExampleApp.Author": "tests.test_builders.make_saved_author",
    }
)
def test_make_instance_prefers_configured_factory() -> None:
    instance = builders.make_instance(Author)
    assert isinstance(instance, Author)
    assert instance.pk is not None
    assert instance.name == "from configured factory"


@override_settings(
    PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES={
        "exampleapp.Author": "tests.test_builders.make_unsaved_author",
    }
)
def test_configured_factory_returning_unsaved_instance_raises() -> None:
    with pytest.raises(ValueError, match="must return a saved Author instance"):
        builders.make_instance(Author)


@override_settings(
    PYTEST_DJANGO_AUTOCHECK_MODELS_FACTORIES={
        "exampleapp.Author": "tests.test_builders.make_wrong_type",
    }
)
def test_configured_factory_returning_wrong_type_raises() -> None:
    with pytest.raises(ValueError, match="must return a saved Author instance"):
        builders.make_instance(Author)


@pytest.mark.django_db
def test_make_instance_falls_back_to_bakery(monkeypatch) -> None:
    monkeypatch.setattr(builders, "_factory_for", lambda model: None)
    instance = builders.make_instance(Author)
    assert isinstance(instance, Author)
    assert instance.pk is not None


def test_discovery_is_noop_without_factory_boy(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "factory.django", None)
    builders._discover_factories.cache_clear()
    assert builders._discover_factories() == {}


def test_factory_base_returns_none_without_factory_boy(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "factory.django", None)
    assert builders._factory_base() is None


def test_import_optional_returns_none_for_missing_module() -> None:
    assert builders._import_optional("nope.does.not.exist") is None
