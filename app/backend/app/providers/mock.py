from __future__ import annotations

from app.core.config import settings
from app.models import Request
from app.providers.base import ProviderStatus


MOCK_CATALOG = {
    "environments": ["dev", "test", "prod"],
    "sites": ["lab-a", "lab-b", "edge-1"],
    "clusters_by_site": {
        "lab-a": ["compute-a", "management-a"],
        "lab-b": ["compute-b"],
        "edge-1": ["edge-cluster"],
    },
    "templates": ["ubuntu-24.04", "windows-server-2022", "rhel-9"],
    "networks": [
        {"name": "dev-vlan-100", "vlan_id": 100, "environments": ["dev"]},
        {"name": "test-vlan-200", "vlan_id": 200, "environments": ["test"]},
        {"name": "prod-vlan-300", "vlan_id": 300, "environments": ["prod"]},
        {"name": "infra-vlan-10", "vlan_id": 10, "environments": ["dev", "test", "prod"]},
    ],
    "datastores": ["ds-lab-a-01", "ds-lab-b-01", "ds-edge-01"],
    "storage_tiers": ["bronze", "silver", "gold"],
}


class MockSourceOfTruthAdapter:
    def health(self) -> ProviderStatus:
        return ProviderStatus(
            name="Mock NetBox/Nautobot",
            kind="source-of-truth",
            mode=settings.provider_mode,
            status="ok",
            capabilities=["catalog", "vm-request-validation"],
            message="Using in-memory mock source-of-truth data.",
        )

    def catalog(self) -> dict:
        return MOCK_CATALOG

    def validate_vm_deployment(self, request: Request) -> list[str]:
        catalog = self.catalog()
        vm = request.vm_deploy
        errors: list[str] = []

        if request.environment not in catalog["environments"]:
            errors.append(f"Unknown environment: {request.environment}")

        if request.site not in catalog["sites"]:
            errors.append(f"Unknown site: {request.site}")

        allowed_clusters = catalog["clusters_by_site"].get(request.site, [])
        if vm.cluster not in allowed_clusters:
            errors.append(f"Cluster {vm.cluster} is not available at site {request.site}")

        if vm.template not in catalog["templates"]:
            errors.append(f"Unknown template: {vm.template}")

        network = next((item for item in catalog["networks"] if item["name"] == vm.network), None)
        if network is None:
            errors.append(f"Unknown network/VLAN: {vm.network}")
        elif request.environment not in network["environments"]:
            errors.append(
                f"Network {vm.network} is not allowed for environment {request.environment}"
            )

        if vm.datastore and vm.datastore not in catalog["datastores"]:
            errors.append(f"Unknown datastore: {vm.datastore}")

        if vm.storage_tier and vm.storage_tier not in catalog["storage_tiers"]:
            errors.append(f"Unknown storage tier: {vm.storage_tier}")

        return errors


class MockVsphereAdapter:
    def health(self) -> ProviderStatus:
        return ProviderStatus(
            name="Mock vSphere",
            kind="virtualization",
            mode=settings.provider_mode,
            status="ok",
            capabilities=["plan-vm-deploy", "execute-vm-deploy"],
            message="Mock adapter only. No vCenter or ESXi calls are made.",
        )

    def plan_vm_deployment(self, request: Request) -> dict:
        vm = request.vm_deploy
        storage_target = vm.datastore or f"tier:{vm.storage_tier}"
        return {
            "dry_run": True,
            "provider": "vsphere.mock",
            "workflow": "vm_deploy_from_template",
            "request_id": request.id,
            "vm_name": vm.vm_name,
            "summary": (
                f"Clone {vm.vm_name} from {vm.template} into {request.site}/{vm.cluster} "
                f"on {storage_target}"
            ),
            "steps": [
                {"name": "resolve-template", "status": "planned", "target": vm.template},
                {
                    "name": "check-placement",
                    "status": "planned",
                    "target": f"{request.site}/{vm.cluster}",
                },
                {"name": "select-storage", "status": "planned", "target": storage_target},
                {"name": "attach-network", "status": "planned", "target": vm.network},
                {"name": "clone-vm", "status": "planned", "target": vm.vm_name},
                {
                    "name": "apply-sizing",
                    "status": "planned",
                    "target": f"{vm.cpu} CPU, {vm.memory_gb} GB RAM, {vm.disk_gb} GB disk",
                },
                {"name": "post-deploy-checks", "status": "planned", "target": "simulated"},
            ],
        }

    def execute_vm_deployment(self, request: Request, plan: dict) -> dict:
        vm = request.vm_deploy
        return {
            "dry_run": False,
            "mock": True,
            "provider": "vsphere.mock",
            "request_id": request.id,
            "vm_name": vm.vm_name,
            "mock_task_id": f"mock-task-{request.id[:8]}",
            "mock_vm_id": f"vm-{request.id[:8]}",
            "message": "Mock VM deployment completed without contacting infrastructure.",
            "executed_steps": [
                {**step, "status": "completed"}
                for step in plan.get("steps", [])
            ],
        }


def provider_statuses() -> list[ProviderStatus]:
    return [
        MockVsphereAdapter().health(),
        MockSourceOfTruthAdapter().health(),
        ProviderStatus(
            name="Mock AWX/Ansible",
            kind="automation",
            mode=settings.provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No AWX calls are made.",
        ),
        ProviderStatus(
            name="Mock Terraform/OpenTofu",
            kind="iac",
            mode=settings.provider_mode,
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
    ]
