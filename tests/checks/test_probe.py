"""Tests for the out-of-process migration probe."""

import os
import subprocess
import sys
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


_THROWAWAY_NAME = "throwaway"


def _fake_connection(name: str) -> MagicMock:
    """Build a connection whose ``create_test_db`` behaves like Django's.

    Django points the connection at the test database once it exists, which
    is what tells the probe that there is something to destroy.
    """
    connection = MagicMock()
    connection.settings_dict = {"NAME": name, "TEST": {}}

    def create_test_db(**kwargs):
        connection.settings_dict["NAME"] = _THROWAWAY_NAME

    connection.creation.create_test_db.side_effect = create_test_db
    return connection


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
    connection = _fake_connection(":memory:")
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK
    connection.creation.create_test_db.assert_called_once()
    connection.creation.destroy_test_db.assert_called_once_with(":memory:", verbosity=0)


def test_main_returns_setup_error_when_create_fails_outside_migrations() -> None:
    connection = _fake_connection("db")
    connection.creation.create_test_db.side_effect = RuntimeError("permission denied")
    with _patch_django(connection):
        assert probe.main() == probe.EXIT_SETUP_ERROR
    # The database was never created: the connection still targets the
    # project's own database, which must never be destroyed.
    connection.creation.destroy_test_db.assert_not_called()


def test_main_returns_migration_error_when_create_fails_in_migrations() -> None:
    connection = _fake_connection("db")

    def broken_migration(*args, **kwargs):
        from django.db.migrations.operations import RunPython

        connection.settings_dict["NAME"] = _THROWAWAY_NAME
        RunPython("not a callable")

    connection.creation.create_test_db.side_effect = broken_migration
    with _patch_django(connection):
        assert probe.main() == probe.EXIT_MIGRATION_ERROR
    # The database exists by the time its migrations fail: it must not leak.
    connection.creation.destroy_test_db.assert_called_once_with("db", verbosity=0)


def test_is_migration_failure_true_for_migrations_frames() -> None:
    from django.db.migrations.operations import RunPython

    try:
        RunPython("not a callable")
    except Exception as exc:  # noqa: BLE001
        assert probe._is_migration_failure(exc) is True


def test_is_migration_failure_false_for_other_frames() -> None:
    try:
        raise ValueError("permission denied")
    except ValueError as exc:
        assert probe._is_migration_failure(exc) is False


def test_main_returns_migration_error_when_cycle_fails() -> None:
    connection = _fake_connection("db")
    with (
        _patch_django(connection),
        patch.object(probe, "run_cycle", side_effect=RuntimeError("irreversible")),
    ):
        assert probe.main() == probe.EXIT_MIGRATION_ERROR
    connection.creation.destroy_test_db.assert_called_once()


def test_main_reports_teardown_failure_without_changing_the_result(capsys) -> None:
    connection = _fake_connection("db")
    connection.creation.destroy_test_db.side_effect = RuntimeError("late")
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK
    assert "RuntimeError: late" in capsys.readouterr().err


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
    connection = _fake_connection(":memory:")
    connection.creation.create_test_db.side_effect = probe._ProbeTimeout()
    with _patch_django(connection):
        assert probe.main() == probe.EXIT_SETUP_ERROR
    connection.creation.destroy_test_db.assert_not_called()


def test_main_destroys_the_database_when_its_migrations_time_out(
    monkeypatch,
) -> None:
    monkeypatch.delenv(probe.PROBE_DEADLINE_ENV, raising=False)
    connection = _fake_connection("db")

    def slow_migration(**kwargs):
        connection.settings_dict["NAME"] = _THROWAWAY_NAME
        raise probe._ProbeTimeout

    connection.creation.create_test_db.side_effect = slow_migration
    with _patch_django(connection):
        assert probe.main() == probe.EXIT_SETUP_ERROR
    connection.creation.destroy_test_db.assert_called_once_with("db", verbosity=0)


def test_main_returns_setup_error_on_cycle_timeout(monkeypatch) -> None:
    monkeypatch.delenv(probe.PROBE_DEADLINE_ENV, raising=False)
    connection = _fake_connection("db")
    with (
        _patch_django(connection),
        patch.object(probe, "run_cycle", side_effect=probe._ProbeTimeout()),
    ):
        assert probe.main() == probe.EXIT_SETUP_ERROR
    connection.creation.destroy_test_db.assert_called_once()


def test_main_cancels_deadline_on_success(monkeypatch) -> None:
    monkeypatch.setenv(probe.PROBE_DEADLINE_ENV, "300")
    _, alarm_calls = _fake_sigalrm(monkeypatch)
    connection = _fake_connection(":memory:")
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK
    assert alarm_calls == [300, 0]


_PROJECT_SETTINGS = """
from pathlib import Path

SECRET_KEY = "probe-project"
DATABASES = {{
    "default": {{
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(Path(__file__).parent / "db.sqlite3"),
        {default_options}
    }},
    {extra_databases}
}}
INSTALLED_APPS = ["django.contrib.contenttypes", "probe_app"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
"""

_INITIAL_MIGRATION = """
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Thing",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50)),
            ],
        ),
    ]
"""

_BROKEN_MIGRATION = """
from django.db import migrations


def forward(apps, schema_editor):
    raise RuntimeError("boom in data migration")


class Migration(migrations.Migration):
    dependencies = [("probe_app", "0001_initial")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
"""

_MODELS = """
from django.db import models


class Thing(models.Model):
    name = models.CharField(max_length=50)
"""


def _run_probe_on_project(
    tmp_path,
    *,
    broken_migration: bool = False,
    default_options: str = "",
    extra_databases: str = "",
) -> subprocess.CompletedProcess:
    """Run the real probe, in a subprocess, on a throwaway Django project."""
    app_dir = tmp_path / "probe_app"
    migrations_dir = app_dir / "migrations"
    migrations_dir.mkdir(parents=True)
    (tmp_path / "probe_settings.py").write_text(
        _PROJECT_SETTINGS.format(
            default_options=default_options, extra_databases=extra_databases
        ),
        encoding="utf-8",
    )
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "models.py").write_text(_MODELS, encoding="utf-8")
    (migrations_dir / "__init__.py").write_text("", encoding="utf-8")
    (migrations_dir / "0001_initial.py").write_text(
        _INITIAL_MIGRATION, encoding="utf-8"
    )
    if broken_migration:
        (migrations_dir / "0002_broken.py").write_text(
            _BROKEN_MIGRATION, encoding="utf-8"
        )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "probe_settings"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), *(entry for entry in sys.path if entry)]
    )
    env.pop(probe.PROBE_DEADLINE_ENV, None)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe.PROBE_COMMAND],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _leftover_databases(tmp_path) -> list[str]:
    return sorted(path.name for path in tmp_path.glob("db.sqlite3*"))


def test_probe_succeeds_and_leaves_no_database_behind(tmp_path) -> None:
    result = _run_probe_on_project(tmp_path)
    assert result.returncode == probe.EXIT_OK, result.stderr
    # Whatever the probe writes to stderr ends up in the findings: the
    # interpreter must not warn about how the probe was launched.
    assert "RuntimeWarning" not in result.stderr
    assert _leftover_databases(tmp_path) == []


def test_probe_destroys_the_database_when_a_forward_migration_fails(
    tmp_path,
) -> None:
    result = _run_probe_on_project(tmp_path, broken_migration=True)
    assert result.returncode == probe.EXIT_MIGRATION_ERROR
    assert "boom in data migration" in result.stderr
    assert _leftover_databases(tmp_path) == []


def test_main_refuses_projects_with_several_databases(capsys) -> None:
    connection = _fake_connection("db")
    django_module = MagicMock()
    db_module = MagicMock()
    db_module.connection = connection
    db_module.connections = ["default", "analytics"]
    with patch.dict("sys.modules", {"django": django_module, "django.db": db_module}):
        assert probe.main() == probe.EXIT_SETUP_ERROR
    assert "analytics, default" in capsys.readouterr().err
    connection.creation.create_test_db.assert_not_called()


def test_probe_refuses_a_project_with_several_databases(tmp_path) -> None:
    result = _run_probe_on_project(
        tmp_path,
        extra_databases=(
            '"analytics": {"ENGINE": "django.db.backends.sqlite3", '
            '"NAME": str(Path(__file__).parent / "analytics.sqlite3")},'
        ),
    )
    assert result.returncode == probe.EXIT_SETUP_ERROR
    assert "several databases (analytics, default)" in result.stderr
    assert _leftover_databases(tmp_path) == []
    assert not (tmp_path / "analytics.sqlite3").exists()


def test_main_forces_migrations_on_the_throwaway_database() -> None:
    connection = _fake_connection("db")
    connection.settings_dict["TEST"]["MIGRATE"] = False
    with _patch_django(connection), patch.object(probe, "run_cycle"):
        assert probe.main() == probe.EXIT_OK
    assert connection.settings_dict["TEST"]["MIGRATE"] is True


def test_probe_succeeds_when_the_project_disables_test_migrations(tmp_path) -> None:
    result = _run_probe_on_project(
        tmp_path, default_options='"TEST": {"MIGRATE": False},'
    )
    assert result.returncode == probe.EXIT_OK, result.stderr
    assert _leftover_databases(tmp_path) == []
