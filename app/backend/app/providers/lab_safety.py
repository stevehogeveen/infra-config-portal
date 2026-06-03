from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class LabSafetyState:
    closed_loop_ack: bool
    readonly_ack: bool
    destructive_ack: bool

    @property
    def readonly_allowed(self) -> bool:
        return self.closed_loop_ack and self.readonly_ack

    @property
    def destructive_allowed(self) -> bool:
        return self.readonly_allowed and self.destructive_ack

    @property
    def blockers(self) -> list[str]:
        blockers: list[str] = []
        if not self.closed_loop_ack:
            blockers.append("LAB_CLOSED_LOOP_ACK=YES is required for real lab probes.")
        if not self.readonly_ack:
            blockers.append("LAB_READONLY_ACK=YES is required for real read-only probes.")
        return blockers

    def as_flags(self) -> dict[str, bool]:
        return {
            "closed_loop_ack": self.closed_loop_ack,
            "readonly_ack": self.readonly_ack,
            "destructive_ack": self.destructive_ack,
            "readonly_allowed": self.readonly_allowed,
            "destructive_allowed": self.destructive_allowed,
        }


def current_lab_safety() -> LabSafetyState:
    return LabSafetyState(
        closed_loop_ack=settings.lab_closed_loop_ack == "YES",
        readonly_ack=settings.lab_readonly_ack == "YES",
        destructive_ack=settings.lab_destructive_ack == "REBUILD_LAB",
    )
