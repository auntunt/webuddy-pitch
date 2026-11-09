"""JSON API routes. Importing this package registers every route, in the order of the module list at the bottom."""
from __future__ import annotations

import re


ROUTES = []


def route(method: str, pattern: str):
    rx = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


from . import (  # noqa: E402,F401  registration order == original route order
    workspace,
    projects,
    knowledge,
    sessions,
    lessons,
    tickets,
    settings,
    runs,
    workbench,
)
