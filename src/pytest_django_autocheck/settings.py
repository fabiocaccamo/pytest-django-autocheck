"""Centralized access to the plugin's configuration.

Every option is read from the project's Django settings under the
``PYTEST_DJANGO_AUTOCHECK_`` prefix and falls back to the default defined here,
so the plugin stays zero-config: a project only overrides what it needs.

Supported settings (the prefix is omitted in this list):

- ``CHECKS`` (list of check names, default ``None``): when set, only the named
  checks run; when ``None`` every registered check runs. Valid names are the
  ones registered by the plugin (``imports``, ``system_checks``,
  ``migrations``, ``models``, ``admin``, ``urls``, ``views``, ``templates``,
  ``management_commands``, ``forms``, ``serializers``).
- ``SKIP`` (list of check names, default ``None``): when set, the named checks
  are excluded from the run. The exclusion is applied after ``CHECKS`` (and
  after ``--autocheck-only``), so a check named in both is skipped.
- ``MIGRATIONS_PROBE_TIMEOUT`` (seconds, default ``300``): maximum time the
  dynamic migration probe subprocess is allowed to run before it is aborted
  and the dynamic step is skipped with a ``WARNING``.
- ``MODELS_EXCLUDE`` (list of ``"app_label.ModelName"`` labels, default
  ``[]``): models excluded from instance building. The ``models`` check skips
  them entirely and the ``admin`` check skips their change view (attribute
  validation, changelist and add views still run). This is the escape hatch
  for models whose domain constraints can never be satisfied by generated
  data (e.g. a ``clean()`` that requires specific related rows, or a CHECK
  constraint between correlated fields). Matching is case-insensitive and
  every exclusion is reported as ``INFO`` so it never disappears silently.
- ``MODELS_FACTORIES`` (dict mapping ``"app_label.ModelName"`` labels to the
  dotted path of a callable, default ``{}``): the callable is imported and
  called with no arguments instead of the generic generator when the
  ``models`` and ``admin`` checks need an instance of that model, and must
  return a *saved* instance. Matching is case-insensitive. A model listed
  here wins over ``MODELS_EXCLUDE``: providing a factory means the model can
  be checked after all, so prefer this over excluding it.
- ``DEPLOY`` (bool, default ``False``): when ``True`` the ``system_checks``
  check also runs Django's deployment checks (``DEBUG``, ``SECRET_KEY``,
  SSL/HSTS, secure cookies, etc.) on top of the regular ones. Off by default
  because those checks fail on development/test settings; enable it for a
  pre-production audit.
"""

import copy
from typing import Any

from django.conf import settings

SETTING_PREFIX = "PYTEST_DJANGO_AUTOCHECK_"

DEFAULTS: dict[str, Any] = {
    "CHECKS": None,
    "SKIP": None,
    "MIGRATIONS_PROBE_TIMEOUT": 300,
    "MODELS_EXCLUDE": [],
    "MODELS_FACTORIES": {},
    "DEPLOY": False,
}


def get_setting(name: str) -> Any:
    """Return the project's value for ``name`` or the documented default.

    ``name`` is the setting key without the ``PYTEST_DJANGO_AUTOCHECK_``
    prefix and must be one of the keys defined in :data:`DEFAULTS`. Defaults
    are returned as shallow copies so a caller mutating the value cannot
    corrupt them for the rest of the process.
    """
    return getattr(settings, SETTING_PREFIX + name, copy.copy(DEFAULTS[name]))
