# Operator Primary Action Safety Map - 2026-07-18

Scope:
- Lab Builder operator-mode surfaces on branch `unified-build-journey`.
- Evidence for the map-first simplification goal: every visible primary action either stays local,
  navigates to the next surface, saves profile/default data only, or runs a cataloged read-only
  workflow action.
- Provider mode for verification: `mock`.
- No hardware contact, live write, RAID apply, firmware apply, factory reset, rebuild, NetApp
  apply, or confirmation-gate change.

## Operator Surface Map

| Surface | Route | Primary operator control | Effect | Catalog action | Catalog mode | UI runnable | Guarded runnable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Overview | `/overview` | Review Build Plan | Navigates to Run Center | none | local navigation | n/a | n/a |
| Lab Defaults | `/setup/defaults` | Save defaults | Saves kit profile/default values only; no workflow starts | none | profile save | n/a | n/a |
| Cisco Switch | `/setup/cisco` (`/network` legacy) | Run Cisco read-only check | Runs the Cisco read-only workflow action | `cisco.ssh-readonly-probe` | `read_only` | yes | no |
| Compute & iLO | `/setup/ilo` (`/server` legacy) | Test DL360 Gen10 | Runs ESXi management validation | `esxi.management-validation` | `read_only` | yes | no |
| Storage & NetApp | `/setup/storage` (`/storage` legacy) | Run NetApp read-only check | Runs NetApp setup preview | `netapp.setup-preview` | `read_only` | yes | no |
| Virtualization | `/setup/esxi` (`/virtualization` legacy) | Test vCenter VCSA / direct ESXi workspace check | Runs vCenter/ESXi readiness when in scope; availability is profile-dependent | `vcenter-netapp.readiness` | `read_only` | profile-dependent | no |
| Firmware | `/setup/firmware` (`/firmware-upgrades` legacy) | Check versions | Runs firmware inventory only | `firmware.inventory` | `read_only` | yes | no |
| Firmware row | `/setup/firmware` | Upgrade | Queues guarded planning only; does not invoke apply | `firmware.upgrade-plan` | `read_only` | yes | no |
| Firmware row | `/setup/firmware` | Bypass | Local decision state only | none | local decision | n/a | n/a |
| Software Media | `/setup/media` / `/setup/ovf` | Check media | Reads filenames and media inventory only | none | read-only inventory endpoint | n/a | n/a |
| Reports | `/reports` (`/validation` legacy) | Run validation | Runs validation summary | `lab-validation.summary` | `read_only` | yes | no |
| Run Center | `/run` (`/run-center` legacy) | Start Build | Starts the ordered build plan runner; guarded steps pause for confirmation before any hardware-changing action | `full-lab.build-plan` | `read_only` | yes | no |

## Registry Metadata Snapshot

Collected with:

```powershell
$env:PROVIDER_MODE='mock'
@'
from app.services.workflow_registry import get_workflow_action
ids = [
    'cisco.ssh-readonly-probe',
    'esxi.management-validation',
    'netapp.setup-preview',
    'vcenter-netapp.readiness',
    'firmware.inventory',
    'firmware.upgrade-plan',
    'lab-validation.summary',
    'full-lab.build-plan',
    'operator-readonly-sweep.real-lab',
]
for action_id in ids:
    action = get_workflow_action(action_id)
    print(f"{action_id}|{action['label']}|{action['mode']}|ui={action['ui_run_supported']}|guarded={action['guarded_run_supported']}|availability={action.get('current_availability')}")
'@ | .\.venv\Scripts\python.exe -
```

Result:

```text
cisco.ssh-readonly-probe|Cisco SSH Read-Only Probe|read_only|ui=True|guarded=False|availability=available
esxi.management-validation|Management Validation|read_only|ui=True|guarded=False|availability=available
netapp.setup-preview|Setup Preview|read_only|ui=True|guarded=False|availability=available
vcenter-netapp.readiness|vCenter-NetApp Readiness|read_only|ui=False|guarded=False|availability=not_in_scope
firmware.inventory|Run Inventory|read_only|ui=True|guarded=False|availability=available
firmware.upgrade-plan|Plan Upgrade|read_only|ui=True|guarded=False|availability=available
lab-validation.summary|Lab Validation Summary|read_only|ui=True|guarded=False|availability=available
full-lab.build-plan|Run Full Lab Build Plan|read_only|ui=True|guarded=False|availability=available
operator-readonly-sweep.real-lab|Run Operator Read-Only Sweep|read_only|ui=True|guarded=False|availability=available
```

Note:
- `vcenter-netapp.readiness` is `not_in_scope` in this backend snapshot because the active profile
  has vCenter disabled. Frontend route tests also cover the vCenter-enabled mocked state; the
  action remains cataloged as `read_only` and `guarded=False`.

## Verification Commands

```powershell
npm run test:e2e -- --grep "operator button matrix keeps default actions simple and safe|operator primary check buttons run only expected read-only workflows|renders the map-first operator spine and pages"
```

Expected/result:
- 3 passed.

```powershell
$env:PROVIDER_MODE='mock'; .\.venv\Scripts\python.exe -m pytest -q tests/test_operator_readonly_sweep.py tests/test_workflow_registry.py::test_safe_read_only_registry_actions_are_ui_runnable tests/test_workflow_registry.py::test_write_destructive_and_unallowlisted_actions_are_not_ui_runnable
```

Expected/result:
- 11 passed.

