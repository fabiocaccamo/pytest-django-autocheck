"""Shared import of the modules an app may or may not ship."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


def import_optional_module(name: str) -> ModuleType | None:
    """Import ``name``, returning ``None`` only when the module does not exist.

    An app is free not to ship a ``forms``, ``serializers`` or ``factories``
    module, so its absence (or the absence of one of its parent packages) is
    not an error. An ``ImportError`` raised *inside* an existing module is a
    real failure and propagates: treating it as "no such module" would
    silently skip everything the module defines.
    """
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        missing = error.name
        if missing is not None and (name == missing or name.startswith(f"{missing}.")):
            return None
        raise
