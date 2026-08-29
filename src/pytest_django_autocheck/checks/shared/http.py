"""Shared HTTP helpers for checks that drive the Django test client."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from django.http import HttpResponse


def same_path_redirect(response: HttpResponse, path: str) -> str | None:
    """Return the Location of a redirect that points back at *path* itself.

    A redirect whose target has the same path (only the scheme or host
    changes, e.g. an SSL or www redirect) means the view was never executed:
    callers report it instead of silently treating the response as healthy.
    Returns ``None`` for non-redirect responses and for redirects to a
    different path (e.g. a login page), which are legitimate.
    """
    if not 300 <= response.status_code < 400:
        return None
    location = response.headers.get("Location", "")
    return location if urlsplit(location).path == path else None
