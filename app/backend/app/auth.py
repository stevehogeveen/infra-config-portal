from __future__ import annotations

from fastapi import Request


def get_current_actor(request: Request) -> str:
    return request.headers.get("X-Mock-User", "local-dev-user")
