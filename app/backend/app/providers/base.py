from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models import Request


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    kind: str
    mode: str
    status: str
    capabilities: list[str]
    message: str


class VsphereAdapter(Protocol):
    def health(self) -> ProviderStatus:
        ...

    def plan_vm_deployment(self, request: Request) -> dict:
        ...

    def execute_vm_deployment(self, request: Request, plan: dict) -> dict:
        ...


class SourceOfTruthAdapter(Protocol):
    def health(self) -> ProviderStatus:
        ...

    def catalog(self) -> dict:
        ...

    def validate_vm_deployment(self, request: Request) -> list[str]:
        ...
