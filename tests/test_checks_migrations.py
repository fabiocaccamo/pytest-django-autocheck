"""Tests for the migrations check (PoC 4.1)."""

import os
import subprocess
from unittest.mock import patch

from django.apps import apps
from django.db.migrations import RunPython, RunSQL
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader

from pytest_django_autocheck.checks.migrations import MigrationsCheck
from pytest_django_autocheck.checks.shared.scope import inspected_labels


def test_check_metadata() -> None:
    check = MigrationsCheck()
    assert check.name == "migrations"
    assert check.severity == "ERROR"


def test_clean_app_has_no_findings() -> None:
    check = MigrationsCheck()
    with patch.object(check, "_inspect_database", return_value=[]):
        findings = check.run([apps.get_app_config("exampleapp")])
    assert findings == []


def test_run_on_whole_project_has_no_errors() -> None:
    check = MigrationsCheck()
    with patch.object(check, "_inspect_database", return_value=[]):
        findings = check.run(None)
    assert [f for f in findings if f.severity == "ERROR"] == []


def test_inspect_runpython_irreversible() -> None:
    check = MigrationsCheck()
    op = RunPython(lambda apps, schema: None)
    findings = check._inspect([op], "app.0001")
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert "RunPython operation at index 0" in findings[0].message


def test_inspect_runpython_noop_reverse() -> None:
    check = MigrationsCheck()
    op = RunPython(lambda apps, schema: None, RunPython.noop)
    findings = check._inspect([op], "app.0001")
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert "RunPython operation at index 0" in findings[0].message


def test_inspect_includes_forward_callable_name() -> None:
    def populate_things(apps, schema_editor):
        pass

    check = MigrationsCheck()
    op = RunPython(populate_things, RunPython.noop)
    findings = check._inspect([op], "app.0001")
    assert "(" in findings[0].message
    assert "populate_things" in findings[0].message


def test_inspect_distinguishes_multiple_noop_operations() -> None:
    check = MigrationsCheck()
    ops = [
        RunPython(lambda apps, schema: None, RunPython.noop),
        RunSQL("SELECT 1;"),
        RunPython(lambda apps, schema: None, RunPython.noop),
    ]
    findings = check._inspect(ops, "app.0001")
    messages = [f.message for f in findings]
    assert len(messages) == len(set(messages)) == 3
    assert "at index 0" in messages[0]
    assert "RunSQL operation at index 1" in messages[1]
    assert "at index 2" in messages[2]


def test_inspect_runpython_with_explicit_reverse_is_clean() -> None:
    check = MigrationsCheck()
    op = RunPython(lambda apps, schema: None, lambda apps, schema: None)
    assert check._inspect([op], "app.0001") == []


def test_inspect_runsql_irreversible() -> None:
    check = MigrationsCheck()
    op = RunSQL("SELECT 1;")
    findings = check._inspect([op], "app.0001")
    assert findings[0].severity == "ERROR"


def test_inspect_runsql_noop_reverse() -> None:
    check = MigrationsCheck()
    op = RunSQL("SELECT 1;", RunSQL.noop)
    findings = check._inspect([op], "app.0001")
    assert findings[0].severity == "WARNING"
    assert "RunSQL operation at index 0" in findings[0].message


def _fake_changes():
    fake_operation = type("FakeOperation", (), {})()
    fake_migration = type("FakeMigration", (), {"operations": [fake_operation]})()
    return {"exampleapp": [fake_migration]}


def test_detect_missing_reports_project_app_changes() -> None:
    check = MigrationsCheck()
    loader = MigrationLoader(None, ignore_no_migrations=True)
    with patch.object(MigrationAutodetector, "changes", return_value=_fake_changes()):
        findings = check._detect_missing(loader, inspected_labels(None))
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "exampleapp"
    assert "makemigrations exampleapp" in findings[0].message
    assert "FakeOperation" in findings[0].message


def test_detect_missing_ignores_non_project_apps() -> None:
    check = MigrationsCheck()
    loader = MigrationLoader(None, ignore_no_migrations=True)
    fake_migration = type("FakeMigration", (), {"operations": []})()
    with patch.object(
        MigrationAutodetector,
        "changes",
        return_value={"auth": [fake_migration]},
    ):
        assert check._detect_missing(loader, inspected_labels(None)) == []


def test_detect_missing_respects_allowed_filter() -> None:
    check = MigrationsCheck()
    loader = MigrationLoader(None, ignore_no_migrations=True)
    with patch.object(MigrationAutodetector, "changes", return_value=_fake_changes()):
        assert check._detect_missing(loader, {"otherapp"}) == []


def test_detect_missing_is_clean_on_the_real_project() -> None:
    check = MigrationsCheck()
    loader = MigrationLoader(None, ignore_no_migrations=True)
    assert check._detect_missing(loader, inspected_labels(None)) == []


def test_replaced_keys_collects_replaced_migrations() -> None:
    class FakeSquash:
        replaces = [("app", "0001"), ("app", "0002")]

    replaced = MigrationsCheck._replaced_keys({("app", "0001_squashed"): FakeSquash()})
    assert replaced == {("app", "0001"), ("app", "0002")}


def test_iter_targets_skips_replaced_and_filtered() -> None:
    disk = {
        ("app", "0001"): "m1",
        ("app", "0002"): "m2",
        ("other", "0001"): "m3",
    }
    replaced = {("app", "0001")}
    allowed = {"app"}
    targets = list(MigrationsCheck._iter_targets(disk, replaced, allowed))
    assert targets == [(("app", "0002"), "m2")]


def test_reversibility_walk_is_scoped_to_project_apps() -> None:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    replaced = MigrationsCheck._replaced_keys(loader.replacements)
    allowed = inspected_labels(None)
    targets = MigrationsCheck._iter_targets(loader.disk_migrations, replaced, allowed)
    app_labels = {key[0] for key, _migration in targets}
    assert app_labels <= {"exampleapp"}
    assert "auth" not in app_labels
    assert "contenttypes" not in app_labels


def test_run_always_invokes_the_dynamic_step() -> None:
    check = MigrationsCheck()
    with patch.object(check, "_inspect_database", return_value=[]) as inspect_database:
        check.run(None)
    inspect_database.assert_called_once()


def _completed(returncode: int, stderr: str = "", stdout: str = ""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_dynamic_check_passes_on_reversible_project() -> None:
    check = MigrationsCheck()
    assert check._inspect_database() == []


def test_dynamic_check_errors_when_cycle_fails() -> None:
    check = MigrationsCheck()
    with patch(
        "subprocess.run",
        return_value=_completed(1, stderr="OperationalError: boom"),
    ):
        findings = check._inspect_database()
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].target == "database"
    assert "boom" in findings[0].message


def test_dynamic_check_warns_on_setup_error() -> None:
    check = MigrationsCheck()
    with patch(
        "subprocess.run",
        return_value=_completed(2, stderr="ImportError: nope"),
    ):
        findings = check._inspect_database()
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].target == "database"


def test_dynamic_check_warns_when_probe_cannot_launch() -> None:
    check = MigrationsCheck()
    with patch("subprocess.run", side_effect=OSError("no exec")):
        findings = check._inspect_database()
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].target == "database"


def test_dynamic_check_warns_when_probe_times_out() -> None:
    check = MigrationsCheck()
    timeout = subprocess.TimeoutExpired(cmd=["probe"], timeout=300)
    with patch("subprocess.run", side_effect=timeout):
        findings = check._inspect_database()
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].target == "database"
    assert "timed out" in findings[0].message
    assert findings[0].exception is timeout


def test_dynamic_check_error_message_falls_back_to_stdout() -> None:
    check = MigrationsCheck()
    with patch(
        "subprocess.run",
        return_value=_completed(1, stdout="written to stdout"),
    ):
        findings = check._inspect_database()
    assert "written to stdout" in findings[0].message


def test_dynamic_check_warns_without_settings_module() -> None:
    check = MigrationsCheck()
    with patch.object(MigrationsCheck, "_subprocess_env", return_value=None):
        findings = check._inspect_database()
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].target == "database"


def test_subprocess_env_propagates_settings_and_path(monkeypatch) -> None:
    from pytest_django_autocheck.checks import migrations as migrations_module

    monkeypatch.setattr(migrations_module.settings, "SETTINGS_MODULE", "proj.settings")
    monkeypatch.setattr(migrations_module.sys, "path", ["/proj", "", "/proj/src"])
    monkeypatch.setenv("PYTHONPATH", "/preexisting")

    env = MigrationsCheck._subprocess_env()

    assert env["DJANGO_SETTINGS_MODULE"] == "proj.settings"
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert "/proj" in parts
    assert "/proj/src" in parts
    assert "/preexisting" in parts
    assert "" not in parts


def test_subprocess_env_returns_none_without_settings_module(monkeypatch) -> None:
    from pytest_django_autocheck.checks import migrations as migrations_module

    monkeypatch.setattr(migrations_module.settings, "SETTINGS_MODULE", None)
    assert MigrationsCheck._subprocess_env() is None
