from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class InlineWorker:
    """Synchronous worker shaped for later replacement with Celery/RQ/Temporal."""

    def run(self, func: Callable[..., T], *args: object, **kwargs: object) -> T:
        return func(*args, **kwargs)
