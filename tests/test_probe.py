"""Tests for the out-of-process migration probe."""

from unittest.mock import MagicMock, patch

import pytest

from pytest_django_autocheck.checks import probe


def _fake_sigalrm(monkeypatch) -> tuple[list, list]:
    """Give ``probe.signal`` a working fake SIGALRM on every platform.

    Returns the recorded ``signal()`` and ``alarm()`` calls. Keeps the alarm
    tests runnable (and the arm/cancel lines covered) on Windows, where the
    real ``signal`` module has no ``SIGALRM``.
    """
    signal_calls: list = []
    alarm_calls: list = []
    monkeypatch.setattr(probe.signal, "SIGALRM", 14, raising=False)
    monkeypatch.setattr(probe.signal, "signal", lambda *args: signal_calls.append(args))
    monkeypatch.setattr(
        probe.signal,
        "alarm",
        lambda seconds: alarm_calls.append(seconds),
        raising=False,
    )
    return signal_calls, alarm_calls


def test_isolated_test_name_for_file_database() -> None:
    assert probe.isolated_test_name("/tmp/db.sqlite3") == "/tmp/db.sqlite3_autocheck"


def test_isolated_test_name_with_token() -> None:
    assert (
        probe.isolated_test_name("/tmp/db.sqlite3", "4242")
        == "/tmp/db.sqlite3_autocheck_4242"
    )


def test_isolated_test_name_for_in_memory_database() -> None:
    assert probe.isolated_test_name(":memory:", "4242") == ":memory:"


def test_isolated_test_name_for_missing_name() -> None:
    assert probe.isolated_test_name(None) is None


def test_run_cycle_reverses_only_project_apps() -> None:
    executor = MagicMock()
    executor.loader.graph.nodes = {("auth", "0001"), ("exampleapp", "0001")}
    executor.loader.graph.leaf_nodes.return_value = [("exampleapp", "0001")]
    connection = MagicMock()

    with patch(
        "django.db.migrations.executor.MigrationExecutor",
        return_value=executor,
    ):
        probe.run_cycle(connection)

    reverse_call, forward_call = executor.migrate.call_args_list
    assert reverse_call.args[0] == [("exampleapp", None)]
    assert forward_call.args[0] == [("exampleapp", "0001")]


def test_run_cycle_reverses_nothing_without_project_apps() -> None:
    executor = MagicMock()
    executor.loader.graph.nodes = {("auth", "0001")}
    executor.loader.graph.leaf_nodes.return_value = [("auth", "0001")]
    connection = MagicMock()

    with patch(
        "django.db.migrations.executor.MigrationExecutor",
        return_value=executor,
    ):
        probe.run_cycle(connection)

    reverse_call, forward_call = executor.migrate.call_args_list
    assert reverse_call.args[0] == []
    assert forward_call.args[0] == [("auth", "0001")]


def _patch_django(connection: MagicMock):
    django_module = MagicMock()
    db_module = MagicMock()
    db_module.connection = connection
    return patch.dict(
        "sys.modules",
        {"django": django_module, "django.db": db_module},
    )


def test_main_returns_setup_error_when_django_setup_fails() -> None:
    django_module = MagicMock()
    django_module.setup.side_effect = RuntimeError("no settings")
    with patch.dict("sys.modules", {"django": django_module}):
        assert probe.main() == probe.EXIT_SETUP_ERROR


def test_main_returns_ok_on_success() -> None:
    connection = MagicMock()
    connection.settings_dict = {"NAME": ":memory:", "TEST": {}}
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK
    connection.creation.create_test_db.assert_called_once()
    connection.creation.destroy_test_db.assert_called_once()


def test_main_returns_migration_error_when_create_fails() -> None:
    connection = MagicMock()
    connection.settings_dict = {"NAME": ":memory:", "TEST": {}}
    connection.creation.create_test_db.side_effect = RuntimeError("boom")
    with _patch_django(connection):
        assert probe.main() == probe.EXIT_MIGRATION_ERROR


def test_main_returns_migration_error_when_cycle_fails() -> None:
    connection = MagicMock()
    connection.settings_dict = {"NAME": "db", "TEST": {}}
    with (
        _patch_django(connection),
        patch.object(probe, "run_cycle", side_effect=RuntimeError("irreversible")),
    ):
        assert probe.main() == probe.EXIT_MIGRATION_ERROR
    connection.creation.destroy_test_db.assert_called_once()


def test_main_swallows_teardown_failure() -> None:
    connection = MagicMock()
    connection.settings_dict = {"NAME": "db", "TEST": {}}
    connection.creation.destroy_test_db.side_effect = RuntimeError("late")
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK


def test_raise_probe_timeout_raises() -> None:
    with pytest.raises(probe._ProbeTimeout):
        probe._raise_probe_timeout(0, None)


def test_arm_deadline_returns_false_without_env(monkeypatch) -> None:
    monkeypatch.delenv(probe.PROBE_DEADLINE_ENV, raising=False)
    assert probe._arm_deadline() is False


def test_arm_deadline_returns_false_for_invalid_value(monkeypatch) -> None:
    monkeypatch.setenv(probe.PROBE_DEADLINE_ENV, "not-a-number")
    _fake_sigalrm(monkeypatch)
    assert probe._arm_deadline() is False


def test_arm_deadline_returns_false_for_non_positive(monkeypatch) -> None:
    monkeypatch.setenv(probe.PROBE_DEADLINE_ENV, "0")
    _fake_sigalrm(monkeypatch)
    assert probe._arm_deadline() is False


def test_arm_deadline_arms_and_cancels_alarm(monkeypatch) -> None:
    monkeypatch.setenv(probe.PROBE_DEADLINE_ENV, "300")
    signal_calls, alarm_calls = _fake_sigalrm(monkeypatch)
    assert probe._arm_deadline() is True
    assert signal_calls == [(14, probe._raise_probe_timeout)]
    assert alarm_calls == [300]
    probe._cancel_deadline(True)
    assert alarm_calls == [300, 0]


def test_arm_deadline_returns_false_without_sigalrm(monkeypatch) -> None:
    monkeypatch.setenv(probe.PROBE_DEADLINE_ENV, "300")
    monkeypatch.delattr(probe.signal, "SIGALRM", raising=False)
    assert probe._arm_deadline() is False


def test_main_returns_setup_error_on_create_timeout(monkeypatch) -> None:
    monkeypatch.delenv(probe.PROBE_DEADLINE_ENV, raising=False)
    connection = MagicMock()
    connection.settings_dict = {"NAME": ":memory:", "TEST": {}}
    connection.creation.create_test_db.side_effect = probe._ProbeTimeout()
    with _patch_django(connection):
        assert probe.main() == probe.EXIT_SETUP_ERROR


def test_main_returns_setup_error_on_cycle_timeout(monkeypatch) -> None:
    monkeypatch.delenv(probe.PROBE_DEADLINE_ENV, raising=False)
    connection = MagicMock()
    connection.settings_dict = {"NAME": "db", "TEST": {}}
    with (
        _patch_django(connection),
        patch.object(probe, "run_cycle", side_effect=probe._ProbeTimeout()),
    ):
        assert probe.main() == probe.EXIT_SETUP_ERROR
    connection.creation.destroy_test_db.assert_called_once()


def test_main_cancels_deadline_on_success(monkeypatch) -> None:
    monkeypatch.setenv(probe.PROBE_DEADLINE_ENV, "300")
    _, alarm_calls = _fake_sigalrm(monkeypatch)
    connection = MagicMock()
    connection.settings_dict = {"NAME": ":memory:", "TEST": {}}
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK
    assert alarm_calls == [300, 0]
