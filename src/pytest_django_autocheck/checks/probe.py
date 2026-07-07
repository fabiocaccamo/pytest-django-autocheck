"""Out-of-process probe that verifies migrations on a throwaway database.

This module is meant to be executed as a subprocess by the migrations check
(``python -m pytest_django_autocheck.checks.probe``). Running it in a separate
process is what makes the dynamic verification possible: the parent pytest
process installs pytest-django's database blocker, which forbids any real
connection; a fresh interpreter has no such blocker and is free to create its
own isolated test database.

The probe creates a dedicated test database (named after the project's database
but with an ``_autocheck`` suffix plus the probe's PID, so it never collides
with the suite's own test database nor with sibling probes spawned by parallel
test runners such as pytest-xdist), applies every migration forward, reverses
the project's own migrations back to zero and applies them forward again.
Third-party and ``django.contrib`` apps are intentionally left applied: their
migrations are not the project's responsibility and some ship irreversible data
migrations that would otherwise break a foreign CI. The throwaway database is
always destroyed afterwards.

Exit codes:

- ``0``: the forward/zero/forward cycle succeeded.
- ``1``: a migration could not be applied or reversed (reported as ``ERROR``).
- ``2``: the environment could not be set up (reported as ``WARNING`` so it
  never breaks a foreign CI).
"""

from __future__ import annotations

import os
import signal
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

EXIT_OK = 0
EXIT_MIGRATION_ERROR = 1
EXIT_SETUP_ERROR = 2

_TEST_NAME_SUFFIX = "_autocheck"

# Seconds the probe is allowed to run before it aborts itself; set by the
# parent so the probe can tear down its throwaway database in a ``finally``
# block instead of being killed and leaking it.
PROBE_DEADLINE_ENV = "PYTEST_DJANGO_AUTOCHECK_PROBE_DEADLINE"


class _ProbeTimeout(Exception):
    """Raised inside the probe when its own deadline elapses."""


def _raise_probe_timeout(signum: int, frame: object) -> None:
    raise _ProbeTimeout


def _arm_deadline() -> bool:
    """Arm a self-abort alarm from ``PROBE_DEADLINE_ENV``; return whether set.

    Returns ``False`` (no deadline) when the variable is unset, not a positive
    number, or the platform has no ``SIGALRM`` (e.g. Windows), so the parent's
    own subprocess timeout remains the only guard there.
    """
    raw = os.environ.get(PROBE_DEADLINE_ENV)
    if not raw or not hasattr(signal, "SIGALRM"):
        return False
    try:
        seconds = int(float(raw))
    except ValueError:
        return False
    if seconds <= 0:
        return False
    signal.signal(signal.SIGALRM, _raise_probe_timeout)
    signal.alarm(seconds)
    return True


def _cancel_deadline(armed: bool) -> None:
    if armed:
        signal.alarm(0)


def isolated_test_name(base_name: str | None, token: str | None = None) -> str | None:
    """Return a dedicated test database name derived from ``base_name``.

    In-memory SQLite databases are returned untouched: each process gets its
    own private database, so no suffix is needed to avoid collisions. When a
    ``token`` is given (typically the probe's PID), it is appended so that
    concurrent probes never target the same database.
    """
    if base_name and base_name != ":memory:":
        suffix = _TEST_NAME_SUFFIX
        if token:
            suffix = f"{suffix}_{token}"
        return f"{base_name}{suffix}"
    return base_name


def run_cycle(connection: BaseDatabaseWrapper) -> None:
    """Reverse the project's migrations to zero, then re-apply them forward.

    Only project apps are reversed; third-party and ``django.contrib`` apps are
    left applied so an irreversible migration the project does not own cannot
    fail the check.
    """
    from django.db.migrations.executor import MigrationExecutor

    from pytest_django_autocheck.checks.shared.scope import project_app_labels

    executor = MigrationExecutor(connection)
    graph_labels = {app_label for app_label, _name in executor.loader.graph.nodes}
    targets = sorted(project_app_labels() & graph_labels)
    executor.migrate([(label, None) for label in targets])

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def main() -> int:
    try:
        import django

        django.setup()
        from django.db import connection
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SETUP_ERROR

    test_settings = connection.settings_dict.setdefault("TEST", {})
    base_name = test_settings.get("NAME") or connection.settings_dict.get("NAME")
    test_settings["NAME"] = isolated_test_name(base_name, str(os.getpid()))

    armed = _arm_deadline()
    try:
        old_config = connection.creation.create_test_db(
            verbosity=0, autoclobber=True, serialize=False
        )
    except _ProbeTimeout:
        _cancel_deadline(armed)
        print(
            "timed out before the throwaway database was ready",
            file=sys.stderr,
        )
        return EXIT_SETUP_ERROR
    except Exception as exc:  # noqa: BLE001
        _cancel_deadline(armed)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_MIGRATION_ERROR

    try:
        run_cycle(connection)
    except _ProbeTimeout:
        print("timed out while verifying migrations", file=sys.stderr)
        result = EXIT_SETUP_ERROR
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        result = EXIT_MIGRATION_ERROR
    else:
        result = EXIT_OK
    finally:
        _cancel_deadline(armed)
        try:
            connection.creation.destroy_test_db(old_config, verbosity=0)
        except Exception:  # noqa: BLE001
            pass

    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
