from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus, SourceOfTruthAdapter, VsphereAdapter
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.mock import MockSourceOfTruthAdapter, MockVsphereAdapter
from app.providers.netapp import NetAppOntapAdapter
from app.services.lab_profiles import active_lab_profile_context
from app.services.status_source import status_source_metadata


class ProviderRegistryError(RuntimeError):
    pass


RECHECK_COMMANDS = {
    "ilo-redfish": "make provider-lab-ilo-reachability",
    "cisco-console": "make provider-lab-cisco-console-ethernet-readiness",
    "cisco-ansible": "make provider-lab-cisco-console-ethernet-readiness",
    "esxi-readonly": "make provider-lab-esxi-install-readiness",
    "netapp-ontap": "make provider-lab-netapp-live-state",
    "mock-vsphere": "make test",
    "mock-source-of-truth": "make test",
    "mock-awx": "make test",
    "mock-opentofu": "make test",
    "mock-network-switch": "make test",
}

EVIDENCE_ARTIFACTS = {
    "ilo-redfish": ["artifacts/codex-runs/ilo-real-run-report.md"],
    "cisco-console": ["artifacts/codex-runs/cisco-4h-lab-run-report.md"],
    "cisco-ansible": ["artifacts/codex-runs/cisco-console-ethernet-readiness-report.md"],
    "esxi-readonly": ["artifacts/codex-runs/esxi-install-readiness-report.md"],
    "netapp-ontap": [
        "artifacts/codex-runs/netapp-live-state-report.md",
        "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
    ],
}

NETWORK_VISIBILITY_PROVIDER_IDS = {
    "ilo-redfish",
    "cisco-console",
    "cisco-ansible",
    "esxi-readonly",
    "netapp-ontap",
}


@dataclass(frozen=True)
class ProviderRegistry:
    provider_mode: str
    vsphere_adapter: VsphereAdapter
    source_of_truth_adapter: SourceOfTruthAdapter
    placeholder_statuses: tuple[ProviderStatus, ...]

    def vsphere(self) -> VsphereAdapter:
        self._ensure_lifecycle_mode()
        return self.vsphere_adapter

    def source_of_truth(self) -> SourceOfTruthAdapter:
        self._ensure_lifecycle_mode()
        return self.source_of_truth_adapter

    def statuses(self, *, lightweight: bool = False) -> list[ProviderStatus]:
        self._ensure_status_mode()
        statuses = [
            self._safe_status(
                "ilo-redfish",
                "HPE iLO / Redfish",
                "hardware-management",
                lambda: IloRedfishAdapter(self.provider_mode).health(),
            ),
            self._safe_status(
                "cisco-console",
                "Cisco Console",
                "network-console",
                lambda: (
                    CiscoConsoleAdapter(self.provider_mode).cached_health()
                    if lightweight
                    else CiscoConsoleAdapter(self.provider_mode).health()
                ),
            ),
            self._safe_status(
                "cisco-ansible",
                "Cisco Ansible SSH",
                "network-automation",
                lambda: CiscoAnsibleAdapter(self.provider_mode).health(),
            ),
            self._safe_status(
                "esxi-readonly",
                "ESXi Read-Only",
                "virtualization",
                lambda: EsxiReadonlyAdapter(self.provider_mode).health(),
            ),
            NetAppOntapAdapter(self.provider_mode).health(),
        ]
        if self.provider_mode == "mock":
            statuses.extend(
                [
                    self.vsphere_adapter.health(),
                    self.source_of_truth_adapter.health(),
                    *self.placeholder_statuses,
                ]
            )
        statuses = [self._with_source_metadata(status) for status in statuses]
        return self._with_control_host_network_gate(statuses)

    def _ensure_lifecycle_mode(self) -> None:
        if self.provider_mode not in {"mock", "local-readonly"}:
            raise ProviderRegistryError(
                f"Provider mode {self.provider_mode!r} is not available. "
                "VM request lifecycle execution is registered only for mock-backed modes."
            )

    def _ensure_status_mode(self) -> None:
        if self.provider_mode not in {"mock", "local-readonly", "local-lab-readwrite"}:
            raise ProviderRegistryError(
                f"Provider mode {self.provider_mode!r} is not available. "
                "Provider status supports only mock, local-readonly, and local-lab-readwrite modes."
            )

    def _safe_status(
        self,
        provider_id: str,
        name: str,
        kind: str,
        factory: Callable[[], ProviderStatus],
    ) -> ProviderStatus:
        try:
            return factory()
        except Exception as exc:
            return ProviderStatus(
                id=provider_id,
                name=name,
                kind=kind,
                mode=self.provider_mode,
                status="blocked",
                capabilities=["health"],
                message="Provider status check failed before any probe was run.",
                blockers=[f"Provider status check failed: {exc.__class__.__name__}."],
                safe_actions=[],
                disabled_actions=[
                    _disabled_action(
                        f"{provider_id}-probe",
                        "Probe",
                        "Probe is disabled because provider status could not be evaluated.",
                    )
                ],
            )

    def _with_source_metadata(self, status: ProviderStatus) -> ProviderStatus:
        source_type = (
            "test_fixture"
            if self.provider_mode == "mock"
            else "live_cached"
            if status.last_probe_time
            else "not_checked"
        )
        metadata = status_source_metadata(
            source_type=source_type,
            checked_at=status.last_probe_time,
            recheck_command=RECHECK_COMMANDS.get(status.id),
            evidence_artifacts=EVIDENCE_ARTIFACTS.get(status.id, []),
            is_operator_visible=source_type != "test_fixture",
        )
        return replace(status, **metadata)

    def _with_control_host_network_gate(
        self, statuses: list[ProviderStatus]
    ) -> list[ProviderStatus]:
        if self.provider_mode == "mock":
            return statuses
        control_host_network = active_lab_profile_context().get("control_host_network") or {}
        if control_host_network.get("status") == "ready":
            return statuses
        return [
            _network_gated_status(status, control_host_network)
            if status.id in NETWORK_VISIBILITY_PROVIDER_IDS
            else status
            for status in statuses
        ]


def provider_registry(provider_mode: str | None = None) -> ProviderRegistry:
    mode = provider_mode or settings.provider_mode
    return ProviderRegistry(
        provider_mode=mode,
        vsphere_adapter=MockVsphereAdapter(mode),
        source_of_truth_adapter=MockSourceOfTruthAdapter(mode),
        placeholder_statuses=_placeholder_statuses(mode),
    )


def provider_registry_error_status(provider_mode: str, message: str) -> ProviderStatus:
    return ProviderStatus(
        id="provider-registry",
        name="Provider Registry",
        kind="control-plane",
        mode=provider_mode,
        status="blocked",
        capabilities=["health"],
        message="Provider registry is blocked; normal lifecycle execution remains mock-only.",
        blockers=[message],
        safe_actions=[],
        disabled_actions=[
            _disabled_action(
                "provider-registry-probe",
                "Probe",
                "Provider probes are disabled until provider mode is corrected.",
            )
        ],
    )


def _placeholder_statuses(provider_mode: str) -> tuple[ProviderStatus, ...]:
    return (
        ProviderStatus(
            id="mock-awx",
            name="Mock AWX/Ansible",
            kind="automation",
            mode=provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No AWX calls are made.",
            disabled_actions=[
                _disabled_action("awx-launch-job", "Launch Job", "AWX job launches are disabled.")
            ],
        ),
        ProviderStatus(
            id="mock-opentofu",
            name="Mock Terraform/OpenTofu",
            kind="iac",
            mode=provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No Terraform or OpenTofu commands are run.",
            disabled_actions=[
                _disabled_action(
                    "iac-apply",
                    "Apply",
                    "Terraform/OpenTofu apply is not exposed.",
                )
            ],
        ),
        ProviderStatus(
            id="mock-network-switch",
            name="Mock Network Switch",
            kind="network",
            mode=provider_mode,
            status="ok",
            capabilities=["health"],
            message="Mock status only. No switch API or CLI calls are made.",
            disabled_actions=[
                _disabled_action(
                    "switch-configure-vlan",
                    "Configure VLAN",
                    "Switch configuration changes are disabled.",
                )
            ],
        ),
    )


def _disabled_action(id_: str, label: str, reason: str) -> ProviderAction:
    return ProviderAction(
        id=id_,
        label=label,
        enabled=False,
        read_only=False,
        reason=reason,
    )


def _network_gated_status(
    status: ProviderStatus, control_host_network: dict[str, object]
) -> ProviderStatus:
    reason = _control_host_blocker(control_host_network)
    safe_actions = [
        replace(action, enabled=False, reason=_with_reason(action.reason, reason))
        for action in status.safe_actions
    ]
    disabled_actions = [
        *status.disabled_actions,
        _disabled_action(
            f"{status.id}-network-visibility",
            "Provider probe",
            reason,
        ),
    ]
    return replace(
        status,
        status="blocked",
        message=f"Not checked from this app host: {reason}",
        source_type="not_checked",
        checked_at=str(control_host_network.get("checked_at") or "") or None,
        freshness="not_checked",
        ttl_seconds=None,
        stale_after_seconds=None,
        is_current=False,
        recheck_command=str(
            control_host_network.get("recheck_command") or "ip -4 -o addr show scope global"
        ),
        configuration={**status.configuration, "control_host_network": control_host_network},
        blockers=_unique([reason, *status.blockers]),
        safe_actions=safe_actions,
        disabled_actions=disabled_actions,
        last_probe_result=None,
        last_probe_time=None,
    )


def _control_host_blocker(control_host_network: dict[str, object]) -> str:
    blockers = control_host_network.get("blockers")
    if isinstance(blockers, list):
        first = next((str(item) for item in blockers if str(item).strip()), "")
        if first:
            return first
    message = str(control_host_network.get("message") or "").strip()
    if message:
        return message
    subnet = str(control_host_network.get("active_subnet") or "the active lab subnet")
    return (
        f"Control host subnet visibility is not checked for {subnet}; "
        "provider status cannot be treated as current."
    )


def _with_reason(existing: str, reason: str) -> str:
    if reason in existing:
        return existing
    if not existing:
        return reason
    return f"{existing} Control host blocker: {reason}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
