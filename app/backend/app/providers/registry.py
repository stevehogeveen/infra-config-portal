from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus, SourceOfTruthAdapter, VsphereAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.mock import MockSourceOfTruthAdapter, MockVsphereAdapter


class ProviderRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRegistry:
    provider_mode: str
    vsphere_adapter: VsphereAdapter
    source_of_truth_adapter: SourceOfTruthAdapter
    placeholder_statuses: tuple[ProviderStatus, ...]

    def vsphere(self) -> VsphereAdapter:
        self._ensure_mock_mode()
        return self.vsphere_adapter

    def source_of_truth(self) -> SourceOfTruthAdapter:
        self._ensure_mock_mode()
        return self.source_of_truth_adapter

    def statuses(self) -> list[ProviderStatus]:
        self._ensure_status_mode()
        return [
            IloRedfishAdapter(self.provider_mode).health(),
            CiscoConsoleAdapter(self.provider_mode).health(),
            self.vsphere_adapter.health(),
            self.source_of_truth_adapter.health(),
            *self.placeholder_statuses,
        ]

    def _ensure_mock_mode(self) -> None:
        if self.provider_mode != "mock":
            raise ProviderRegistryError(
                f"Provider mode {self.provider_mode!r} is not available. "
                "VM request lifecycle execution is registered only for mock mode."
            )

    def _ensure_status_mode(self) -> None:
        if self.provider_mode not in {"mock", "local-readonly"}:
            raise ProviderRegistryError(
                f"Provider mode {self.provider_mode!r} is not available. "
                "Provider status supports only mock and local-readonly modes."
            )


def provider_registry(provider_mode: str | None = None) -> ProviderRegistry:
    mode = provider_mode or settings.provider_mode
    return ProviderRegistry(
        provider_mode=mode,
        vsphere_adapter=MockVsphereAdapter(mode),
        source_of_truth_adapter=MockSourceOfTruthAdapter(mode),
        placeholder_statuses=_placeholder_statuses(mode),
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
            id="mock-netapp",
            name="Mock NetApp ONTAP",
            kind="storage",
            mode=provider_mode,
            status="ok",
            capabilities=["health"],
            message="Mock status only. No ONTAP calls are made.",
            disabled_actions=[
                _disabled_action(
                    "netapp-provision-storage",
                    "Provision Storage",
                    "ONTAP provisioning actions are disabled.",
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
