"""Tests for the centralized settings accessor."""

from django.test import override_settings

from pytest_django_autocheck import settings as conf


def test_default_is_returned_when_unset() -> None:
    assert conf.get_setting("CHECKS") is None


@override_settings(PYTEST_DJANGO_AUTOCHECK_CHECKS=["imports", "models"])
def test_project_override_is_returned() -> None:
    assert conf.get_setting("CHECKS") == ["imports", "models"]


def test_prefix_and_defaults_contract() -> None:
    assert conf.SETTING_PREFIX == "PYTEST_DJANGO_AUTOCHECK_"
    assert set(conf.DEFAULTS) == {
        "CHECKS",
        "SKIP",
        "MIGRATIONS_PROBE_TIMEOUT",
        "MODELS_EXCLUDE",
        "MODELS_FACTORIES",
        "DEPLOY",
    }


def test_models_exclude_defaults_to_empty_list() -> None:
    assert conf.get_setting("MODELS_EXCLUDE") == []


def test_models_factories_defaults_to_empty_dict() -> None:
    assert conf.get_setting("MODELS_FACTORIES") == {}


def test_mutating_a_returned_default_does_not_leak() -> None:
    conf.get_setting("MODELS_EXCLUDE").append("polluted")
    assert conf.get_setting("MODELS_EXCLUDE") == []
