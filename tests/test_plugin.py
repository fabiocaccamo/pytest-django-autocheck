"""Tests for the plugin entry point and option registration."""

import os
import types

import pytest
from _pytest.outcomes import Failed

from pytest_django_autocheck import __version__, plugin
from pytest_django_autocheck.registry import Finding


def test_version_is_exposed() -> None:
    assert isinstance(__version__, str)


def test_modifyitems_is_a_noop_when_disabled() -> None:
    config = types.SimpleNamespace(
        option=types.SimpleNamespace(
            autocheck=False, autocheck_only=[], autocheck_skip=[]
        )
    )
    items = ["sentinel"]
    plugin.pytest_collection_modifyitems(session=None, config=config, items=items)
    assert items == ["sentinel"]


def test_modifyitems_honors_only_and_skip(monkeypatch) -> None:
    config = types.SimpleNamespace(
        option=types.SimpleNamespace(
            autocheck=True,
            autocheck_only=["imports", "models", "admin"],
            autocheck_skip=["models"],
        )
    )
    monkeypatch.setattr(
        plugin, "_build_item", lambda session, check: f"item::{check.name}"
    )
    items: list[object] = []
    plugin.pytest_collection_modifyitems(session="session", config=config, items=items)
    assert items == ["item::imports", "item::admin"]


def test_autocheck_items_are_injected(pytestconfig) -> None:
    # The library dogfoods its own plugin: --autocheck is enabled in addopts,
    # so the session must contain one synthetic item per built-in check.
    assert pytestconfig.option.autocheck is True


def test_run_check_item_passes_when_no_findings() -> None:
    class Clean:
        name = "clean"

        def run(self, app_configs):
            return []

    plugin._run_check_item(Clean())


def test_run_check_item_warns_on_non_error_findings() -> None:
    class Warning_:
        name = "warner"

        def run(self, app_configs):
            return [Finding("warner", "WARNING", "t", "just a warning")]

    with pytest.warns(plugin.AutocheckWarning, match="just a warning"):
        plugin._run_check_item(Warning_())


def test_run_check_item_fails_on_error() -> None:
    class Failing:
        name = "failing"

        def run(self, app_configs):
            return [Finding("failing", "ERROR", "app.Model", "boom")]

    with pytest.raises(Failed):
        plugin._run_check_item(Failing())


def test_run_check_item_reports_warnings_alongside_errors() -> None:
    class Mixed:
        name = "mixed"

        def run(self, app_configs):
            return [
                Finding("mixed", "ERROR", "app.Model", "boom"),
                Finding("mixed", "WARNING", "app.Other", "careful"),
            ]

    with (
        pytest.warns(plugin.AutocheckWarning, match="careful"),
        pytest.raises(Failed, match="boom"),
    ):
        plugin._run_check_item(Mixed())


_MANAGE_PY = (
    "#!/usr/bin/env python\n"
    "import os\n"
    "def main():\n"
    "    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')\n"
)


class _FakeConfig:
    def __init__(self, ini_value="", raises=False):
        self._ini_value = ini_value
        self._raises = raises

    def getini(self, name):
        if self._raises:
            raise KeyError(name)
        return self._ini_value


def _clear_settings_env(monkeypatch) -> None:
    monkeypatch.delenv(plugin._SETTINGS_ENV, raising=False)


def test_read_settings_module_parses_manage_py(tmp_path) -> None:
    manage = tmp_path / "manage.py"
    manage.write_text(_MANAGE_PY, encoding="utf-8")
    assert plugin._read_settings_module(manage) == "myproject.settings"


def test_read_settings_module_returns_none_without_match(tmp_path) -> None:
    manage = tmp_path / "manage.py"
    manage.write_text("print('hello')\n", encoding="utf-8")
    assert plugin._read_settings_module(manage) is None


def test_read_settings_module_returns_none_on_oserror(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.py"
    assert plugin._read_settings_module(missing) is None


def test_find_manage_py_locates_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manage.py").write_text(_MANAGE_PY, encoding="utf-8")
    found = plugin._find_manage_py([])
    assert found == tmp_path / "manage.py"


def test_find_manage_py_searches_arg_parents(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manage.py").write_text(_MANAGE_PY, encoding="utf-8")
    nested = tmp_path / "app" / "tests"
    nested.mkdir(parents=True)
    found = plugin._find_manage_py([str(nested / "test_x.py"), "-v"])
    assert found == tmp_path / "manage.py"


def test_find_manage_py_returns_none_when_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert plugin._find_manage_py([]) is None


def test_autodiscover_settings_sets_env_and_path(tmp_path, monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plugin.sys, "path", list(plugin.sys.path))
    (tmp_path / "manage.py").write_text(_MANAGE_PY, encoding="utf-8")

    plugin._autodiscover_settings([])

    assert os.environ[plugin._SETTINGS_ENV] == "myproject.settings"
    assert str(tmp_path) in plugin.sys.path

    # A second call is a no-op for sys.path (already present).
    plugin._autodiscover_settings([])
    assert plugin.sys.path.count(str(tmp_path)) == 1


def test_autodiscover_settings_noop_without_manage_py(tmp_path, monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    plugin._autodiscover_settings([])
    assert plugin._SETTINGS_ENV not in os.environ


def test_autodiscover_settings_noop_without_settings(tmp_path, monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manage.py").write_text("print('hi')\n", encoding="utf-8")
    plugin._autodiscover_settings([])
    assert plugin._SETTINGS_ENV not in os.environ


def test_settings_already_configured_env(monkeypatch) -> None:
    monkeypatch.setenv(plugin._SETTINGS_ENV, "x.settings")
    assert plugin._settings_already_configured(_FakeConfig(), []) is True


def test_settings_already_configured_ds_arg(monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    assert (
        plugin._settings_already_configured(_FakeConfig(), ["--ds=x.settings"]) is True
    )
    assert plugin._settings_already_configured(_FakeConfig(), ["--ds"]) is True


def test_settings_already_configured_ini(monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    assert plugin._settings_already_configured(_FakeConfig("x.settings"), []) is True


def test_settings_already_configured_false(monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    assert plugin._settings_already_configured(_FakeConfig(""), []) is False


def test_settings_already_configured_getini_raises(monkeypatch) -> None:
    _clear_settings_env(monkeypatch)
    assert plugin._settings_already_configured(_FakeConfig(raises=True), []) is False


def test_load_initial_conftests_skips_without_autocheck(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(
        plugin, "_autodiscover_settings", lambda args: called.append(args)
    )
    plugin.pytest_load_initial_conftests(_FakeConfig(), None, ["-v"])
    assert called == []


def test_load_initial_conftests_skips_when_configured(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(
        plugin, "_autodiscover_settings", lambda args: called.append(args)
    )
    monkeypatch.setattr(plugin, "_settings_already_configured", lambda c, a: True)
    plugin.pytest_load_initial_conftests(_FakeConfig(), None, ["--autocheck"])
    assert called == []


def test_load_initial_conftests_discovers_when_unconfigured(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(
        plugin, "_autodiscover_settings", lambda args: called.append(args)
    )
    monkeypatch.setattr(plugin, "_settings_already_configured", lambda c, a: False)
    plugin.pytest_load_initial_conftests(_FakeConfig(), None, ["--autocheck"])
    assert called == [["--autocheck"]]
