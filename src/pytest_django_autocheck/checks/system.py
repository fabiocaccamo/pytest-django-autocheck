"""Check: Django's own system check framework reports no problems.

The project may register custom system checks and every Django app ships its
own (model, field, admin, template and security checks). Running
``django.core.checks.run_checks`` and mapping each ``CheckMessage`` into a
``Finding`` surfaces those problems through the same report as every other
autocheck: ``ERROR``/``CRITICAL`` messages fail the run, ``WARNING`` and
``INFO``/``DEBUG`` are shown alongside.

The check is a thin adapter: it adds no rules of its own, it only forwards the
``app_configs`` restriction to Django and translates severities.

Unlike the other checks, this one does **not** restrict itself to project apps:
when no ``app_configs`` filter is given it runs every registered system check,
exactly like ``manage.py check``. This is intentional: many system checks are
global (security, caches, cross-app model clashes) and would lose their value
if scoped to a single app, so a third-party ``WARNING`` may legitimately
surface here. Use ``--autocheck-only`` or the ``CHECKS`` setting to opt out.

Deployment checks (``DEBUG``, ``SECRET_KEY``, SSL/HSTS, secure cookies) are
off by default because they fail on development/test settings; set
``PYTEST_DJANGO_AUTOCHECK_DEPLOY = True`` to include them for a pre-production
audit.
"""

from typing import TYPE_CHECKING

from django.core import checks as django_checks

from pytest_django_autocheck.registry import BaseCheck, Finding, Severity
from pytest_django_autocheck.settings import get_setting

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps.config import AppConfig
    from django.core.checks import CheckMessage


class SystemChecksCheck(BaseCheck):
    name = "system_checks"
    severity = "ERROR"

    def run(self, app_configs: Sequence[AppConfig] | None) -> list[Finding]:
        messages = django_checks.run_checks(
            app_configs=app_configs,
            include_deployment_checks=bool(get_setting("DEPLOY")),
        )
        return [self._to_finding(message) for message in messages]

    def _to_finding(self, message: CheckMessage) -> Finding:
        if message.obj is not None:
            target = str(message.obj)
        else:
            target = message.id or "system"
        text = message.msg
        if message.hint:
            text = f"{text} (hint: {message.hint})"
        if message.id:
            text = f"[{message.id}] {text}"
        return Finding(self.name, self._severity_for(message.level), target, text)

    @staticmethod
    def _severity_for(level: int) -> Severity:
        if level >= django_checks.ERROR:
            return "ERROR"
        if level >= django_checks.WARNING:
            return "WARNING"
        return "INFO"
