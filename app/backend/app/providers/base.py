from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models import Request


@dataclass(frozen=True)
class ProviderAction:
    id: str
    label: str
    enabled: bool
    read_only: bool
    reason: str
    method: str | None = None
    endpoint: str | None = None


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    kind: str
    mode: str
    status: str
    capabilities: list[str]
    message: str
    id: str = ""
    configuration: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe_actions: list[ProviderAction] = field(default_factory=list)
    disabled_actions: list[ProviderAction] = field(default_factory=list)
    last_probe_result: dict[str, Any] | None = None
    last_probe_time: str | None = None


class ProviderAdapter(Protocol):
    def health(self) -> ProviderStatus:
        ...


class ReadOnlyProbeAdapter(Protocol):
    def health(self) -> ProviderStatus:
        ...

    def probe(self) -> dict[str, Any]:
        ...


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
