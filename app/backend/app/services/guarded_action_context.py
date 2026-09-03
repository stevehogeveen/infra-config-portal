from __future__ import annotations

import os
from dataclasses import dataclass

from app.services.env_utils import bool_value


@dataclass(frozen=True)
class GuardedActionContext:
    action_id: str
    confirmed_gates: tuple[tuple[str, str], ...] = ()
    confirmation_phrase: str | None = None

    def gate_value(self, name: str) -> str | None:
        return next((value for key, value in self.confirmed_gates if key == name), None)


def guarded_value(
    name: str,
    *,
    action_id: str,
    context: GuardedActionContext | None,
) -> str | None:
    if context is not None and context.action_id == action_id:
        value = context.gate_value(name)
        if value is not None:
            return value
    return os.getenv(name)


def guarded_flag(
    name: str,
    *,
    action_id: str,
    context: GuardedActionContext | None,
) -> bool:
    return bool_value(guarded_value(name, action_id=action_id, context=context))


def guarded_confirmation(
    name: str,
    *,
    action_id: str,
    context: GuardedActionContext | None,
) -> str | None:
    if context is not None and context.action_id == action_id and context.confirmation_phrase is not None:
        return context.confirmation_phrase
    return os.getenv(name)
