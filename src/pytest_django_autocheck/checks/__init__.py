"""Built-in checks.

Importing this package registers all built-in checks on the shared registry.
Registration order is the order in which findings are reported; each check runs
as its own isolated pytest item, so the order never affects correctness.
"""

from pytest_django_autocheck.checks.admin import AdminCheck
from pytest_django_autocheck.checks.commands import ManagementCommandsCheck
from pytest_django_autocheck.checks.forms import FormsCheck
from pytest_django_autocheck.checks.imports import ImportsCheck
from pytest_django_autocheck.checks.migrations import MigrationsCheck
from pytest_django_autocheck.checks.models import ModelsCheck
from pytest_django_autocheck.checks.serializers import SerializersCheck
from pytest_django_autocheck.checks.system import SystemChecksCheck
from pytest_django_autocheck.checks.templates import TemplatesCheck
from pytest_django_autocheck.checks.urls import UrlsCheck
from pytest_django_autocheck.checks.views import ViewsCheck
from pytest_django_autocheck.registry import registry

registry.register(ImportsCheck())
registry.register(SystemChecksCheck())
registry.register(MigrationsCheck())
registry.register(ModelsCheck())
registry.register(AdminCheck())
registry.register(UrlsCheck())
registry.register(ViewsCheck())
registry.register(TemplatesCheck())
registry.register(ManagementCommandsCheck())
registry.register(FormsCheck())
registry.register(SerializersCheck())

__all__ = [
    "AdminCheck",
    "FormsCheck",
    "ImportsCheck",
    "ManagementCommandsCheck",
    "MigrationsCheck",
    "ModelsCheck",
    "SerializersCheck",
    "SystemChecksCheck",
    "TemplatesCheck",
    "UrlsCheck",
    "ViewsCheck",
]
