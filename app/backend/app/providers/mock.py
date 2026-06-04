from __future__ import annotations

from app.core.config import settings
from app.models import Request
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.netapp import NetAppOntapAdapter


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

MOCK_STAGE_EVENTS = [
    {
        "stage": "DISCOVER",
        "status": "completed",
        "message": "Mock catalog and template discovery completed.",
    },
    {
        "stage": "VALIDATE",
        "status": "completed",
        "message": "Mock request validation completed.",
    },
    {
        "stage": "PLAN",
        "status": "completed",
        "message": "Dry-run VM deployment plan generated.",
    },
    {
        "stage": "REVIEW",
        "status": "pending",
        "message": "Operator review is required before mock execution.",
    },
    {
        "stage": "EXECUTE",
        "status": "blocked",
        "message": "Execution waits for explicit operator action.",
    },
    {
        "stage": "COMPLETE",
        "status": "pending",
        "message": "Completion summary will be written after execution.",
    },
    {
        "stage": "BLOCKED",
        "status": "not_applicable",
        "message": "No blocker has been raised for this mock plan.",
    },
]


def _completed_stage_events(plan: dict) -> list[dict]:
    stage_events = plan.get("stage_events")
    if not isinstance(stage_events, list):
        stage_events = MOCK_STAGE_EVENTS

    completed_events: list[dict] = []
    for event in stage_events:
        if not isinstance(event, dict):
            continue
        stage = event.get("stage")
        if stage == "BLOCKED":
            completed_events.append(
                {
                    **event,
                    "status": "not_applicable",
                    "message": "Mock execution completed without blockers.",
                }
            )
        else:
            completed_events.append({**event, "status": "completed"})
    return completed_events


class MockSourceOfTruthAdapter:
    def __init__(self, provider_mode: str | None = None) -> None:
        self.provider_mode = provider_mode or settings.provider_mode

    def health(self) -> ProviderStatus:
        return ProviderStatus(
            id="mock-source-of-truth",
            name="Mock NetBox/Nautobot",
            kind="source-of-truth",
            mode=self.provider_mode,
            status="ok",
            capabilities=["catalog", "vm-request-validation"],
            message="Using in-memory mock source-of-truth data.",
            safe_actions=[],
            disabled_actions=_source_of_truth_disabled_actions(),
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
    def __init__(self, provider_mode: str | None = None) -> None:
        self.provider_mode = provider_mode or settings.provider_mode

    def health(self) -> ProviderStatus:
        return ProviderStatus(
            id="mock-vsphere",
            name="Mock vSphere",
            kind="virtualization",
            mode=self.provider_mode,
            status="ok",
            capabilities=["plan-vm-deploy", "execute-vm-deploy"],
            message="Mock adapter only. No vCenter or ESXi calls are made.",
            safe_actions=[],
            disabled_actions=_vsphere_disabled_actions(),
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
            "mock_only": True,
            "review_before_execute": {
                "required": True,
                "status": "pending",
                "message": "Review the dry-run plan before launching mock execution.",
            },
            "stage_events": MOCK_STAGE_EVENTS,
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
            "stage_events": _completed_stage_events(plan),
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
            id="mock-awx",
            name="Mock AWX/Ansible",
            kind="automation",
            mode=settings.provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No AWX calls are made.",
            disabled_actions=_awx_disabled_actions(),
        ),
        ProviderStatus(
            id="mock-opentofu",
            name="Mock Terraform/OpenTofu",
            kind="iac",
            mode=settings.provider_mode,
            status="ok",
            capabilities=["health"],
            message="Placeholder mock status. No Terraform or OpenTofu commands are run.",
            disabled_actions=_iac_disabled_actions(),
        ),
        ProviderStatus(
            id="ilo-redfish",
            name="HPE iLO/Redfish",
            kind="hardware-management",
            mode="placeholder",
            status="not-configured",
            capabilities=["health"],
            message="Placeholder only. Real Redfish configuration is intentionally absent.",
            disabled_actions=_ilo_placeholder_disabled_actions(),
        ),
        NetAppOntapAdapter(settings.provider_mode).health(),
        ProviderStatus(
            id="mock-network-switch",
            name="Mock Network Switch",
            kind="network",
            mode=settings.provider_mode,
            status="ok",
            capabilities=["health"],
            message="Mock status only. No switch API or CLI calls are made.",
            disabled_actions=_switch_disabled_actions(),
        ),
    ]


def _disabled_action(id_: str, label: str, reason: str) -> ProviderAction:
    return ProviderAction(
        id=id_,
        label=label,
        enabled=False,
        read_only=False,
        reason=reason,
    )


def _vsphere_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action(
            "vsphere-real-clone",
            "Real Clone",
            "Real vCenter clone operations remain unavailable in mock mode.",
        ),
        _disabled_action(
            "vsphere-power-action",
            "Power Action",
            "VM power operations are not exposed by this preview.",
        ),
    ]


def _source_of_truth_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action(
            "source-of-truth-write",
            "Write Record",
            "Source-of-truth writes are not exposed.",
        )
    ]


def _awx_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action("awx-launch-job", "Launch Job", "AWX job launches are disabled.")
    ]


def _iac_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action(
            "iac-apply",
            "Apply",
            "Terraform/OpenTofu apply is not exposed.",
        )
    ]


def _ilo_placeholder_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action(
            "ilo-power-action",
            "Power Action",
            "Power actions are disabled.",
        )
    ]


def _netapp_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action(
            "netapp-provision-storage",
            "Provision Storage",
            "ONTAP provisioning actions are disabled.",
        )
    ]


def _switch_disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action(
            "switch-configure-vlan",
            "Configure VLAN",
            "Switch configuration changes are disabled.",
        )
    ]
