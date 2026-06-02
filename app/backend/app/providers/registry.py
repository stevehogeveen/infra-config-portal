from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.providers.base import ProviderStatus, SourceOfTruthAdapter, VsphereAdapter
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
        self._ensure_mock_mode()
        return [
            self.vsphere_adapter.health(),
            self.source_of_truth_adapter.health(),
            *self.placeholder_statuses,
        ]

    def _ensure_mock_mode(self) -> None:
        if self.provider_mode != "mock":
            raise ProviderRegistryError(
                f"Provider mode {self.provider_mode!r} is not available. "
                "Only mock providers are registered in this MVP."
            )


def provider_registry(provider_mode: str | None = None) -> ProviderRegistry:
    mode = provider_mode or settings.provider_mode
    return ProviderRegistry(
        provider_mode=mode,
        vsphere_adapter=MockVsphereAdapter(),
        source_of_truth_adapter=MockSourceOfTruthAdapter(),
        placeholder_statuses=_placeholder_statuses(mode),
    )


def _placeholder_statuses(provider_mode: str) -> tuple[ProviderStatus, ...]:
    return (
        ProviderStatus(
            name="Mock AWX/Ansible",
            kind="automation",
            mode=provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No AWX calls are made.",
        ),
        ProviderStatus(
            name="Mock Terraform/OpenTofu",
            kind="iac",
            mode=provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No Terraform or OpenTofu commands are run.",
        ),
        ProviderStatus(
            name="HPE iLO/Redfish",
            kind="hardware-management",
            mode="placeholder",
            status="not-configured",
            capabilities=["health"],
            message="Placeholder only. Real Redfish configuration is intentionally absent.",
        ),
        ProviderStatus(
            name="NetApp ONTAP",
            kind="storage",
            mode="placeholder",
            status="not-configured",
            capabilities=["health"],
            message="Placeholder only. Real ONTAP configuration is intentionally absent.",
        ),
        ProviderStatus(
            name="Network Switch",
            kind="network",
            mode="placeholder",
            status="not-configured",
            capabilities=["health"],
            message="Placeholder only. Real switch configuration is intentionally absent.",
        ),
    )
