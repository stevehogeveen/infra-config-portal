from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus, SourceOfTruthAdapter, VsphereAdapter
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.mock import MockSourceOfTruthAdapter, MockVsphereAdapter
from app.providers.netapp import NetAppOntapAdapter


class ProviderRegistryError(RuntimeError):
    pass


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

    def statuses(self) -> list[ProviderStatus]:
        self._ensure_status_mode()
        return [
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
                lambda: CiscoConsoleAdapter(self.provider_mode).health(),
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
            self.vsphere_adapter.health(),
            self.source_of_truth_adapter.health(),
            NetAppOntapAdapter(self.provider_mode).health(),
            *self.placeholder_statuses,
        ]

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
