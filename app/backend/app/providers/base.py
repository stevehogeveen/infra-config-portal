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
    source_type: str = "not_checked"
    checked_at: str | None = None
    freshness: str = "unknown"
    ttl_seconds: int | None = None
    stale_after_seconds: int | None = None
    is_current: bool = False
    is_operator_visible: bool = True
    recheck_command: str | None = None
    evidence_artifacts: list[str] = field(default_factory=list)
    configuration: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe_actions: list[ProviderAction] = field(default_factory=list)
    disabled_actions: list[ProviderAction] = field(default_factory=list)
    last_probe_result: dict[str, Any] | None = None
    last_probe_time: str | None = None


FORBIDDEN_PLAN_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "credential",
    "authorization",
    "cookie",
)


def validate_vm_deployment_plan_contract(plan: Any, request: Request | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["VM deployment plan must be a JSON object."]

    if plan.get("dry_run") is not True:
        errors.append("VM deployment plan must set dry_run=true.")
    if plan.get("mock_only") is not True:
        errors.append("VM deployment plan must set mock_only=true.")
    if not _non_empty_string(plan.get("provider")):
        errors.append("VM deployment plan must include a provider string.")
    if not _non_empty_string(plan.get("workflow")):
        errors.append("VM deployment plan must include a workflow string.")
    if request is not None and plan.get("request_id") != request.id:
        errors.append("VM deployment plan request_id must match the request.")

    review = plan.get("review_before_execute")
    if not isinstance(review, dict) or review.get("required") is not True:
        errors.append("VM deployment plan must require review_before_execute.")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("VM deployment plan must include at least one planned step.")
    elif not all(isinstance(step, dict) and _non_empty_string(step.get("name")) for step in steps):
        errors.append("VM deployment plan steps must be objects with names.")

    stage_events = plan.get("stage_events")
    if not isinstance(stage_events, list) or not stage_events:
        errors.append("VM deployment plan must include stage_events.")
    elif not all(isinstance(event, dict) and _non_empty_string(event.get("stage")) for event in stage_events):
        errors.append("VM deployment plan stage_events must be objects with stages.")

    if _contains_forbidden_plan_key(plan):
        errors.append("VM deployment plan must not contain secret-like keys.")

    return errors


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _contains_forbidden_plan_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if any(fragment in str(key).lower() for fragment in FORBIDDEN_PLAN_KEY_FRAGMENTS):
                return True
            if _contains_forbidden_plan_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_plan_key(item) for item in value)
    return False


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
