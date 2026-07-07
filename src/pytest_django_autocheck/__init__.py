"""pytest-django-autocheck.

Zero-config pytest plugin that runs generic safety checks on any Django project
already configured with pytest-django, without requiring the developer to write
any test. The full set of built-in checks is registered in the ``checks``
subpackage.
"""

from pytest_django_autocheck.metadata import __version__
from pytest_django_autocheck.registry import (
    BaseCheck,
    Check,
    CheckRegistry,
    Finding,
    Severity,
    registry,
)

__all__ = [
    "BaseCheck",
    "Check",
    "CheckRegistry",
    "Finding",
    "Severity",
    "registry",
    "__version__",
]
