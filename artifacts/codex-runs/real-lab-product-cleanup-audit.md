# Real-Lab Product Cleanup Audit

- Run time: 2026-06-10 16:22:22 EDT
- Scope: `/home/administrator/infra-config-portal`
- Mode: real-lab product cleanup, read-only/status verification
- Safety: credentials and environment values were not printed; generated evidence stays redacted

## Skills Applied

- `lab-builder-skill-steward`
- `lab-builder-real-runtime`
- `lab-builder-ux`
- `lab-builder-product-craft`
- `lab-builder-hardware-run`
- `lab-builder-report-remediation`
- `lab-builder-toolchain`
- `lab-builder-dual-app-architecture`

## Operator UI Audit

### Removed Or Reduced

- Removed `Lab Profile` as a visible top-level navigation concept.
- Renamed the normal saved-profile surface to `Active Lab Setup` / `Saved Lab Setups`.
- Replaced the old provider landing route with a direct `Hardware` route.
- Moved detailed provider workflow material under collapsed `Advanced diagnostics`, `Actions / Configs`, and `Advanced / Evidence` disclosures.
- Converted visible `mock`, `test fixture`, `dry-run`, and `global profile` wording in operator views to `Test Mode`, `preview`, and `lab setup` wording.
- Reduced side-nav success/review badges so the sidebar does not read like a report wall.

### Added Or Reshaped

- Added one shell-level `Edit Config` button for the active lab setup.
- Added a right-side config drawer covering subnet, gateway, DNS, NTP, domain, VLAN, MTU, storage protocol, DNS/NTP/SNMP toggles, IPv6 policy, legacy protocol policy, core device IPs, and NetApp IPs/LIFs when in scope.
- Added `block_legacy_protocols` to the lab setup feature model and API payloads.
- Replaced bulky hardware blocks with a compact hardware inventory table.
- Added per-equipment `Actions / Configs` dropdowns with compact options and collapsed proof.
- Kept provider control sections in the intended order: firmware line, access/test controls, saved config summary, actions/configs, collapsed proof.

## Current Real-State Sweep

### iLO Reachability

- Command: `make provider-lab-ilo-reachability`
- Result: completed
- Fresh artifact: `artifacts/real-lab/ilo-reachability-20260610T194452Z.md`
- Classification: `redfish_root_available`
- Important detail: the active setup target candidate timed out/filtered, but the fallback/control-access original DHCP candidate reached Redfish root.
- Next action from artifact: proceed to iLO authentication and inventory.

### Cisco Readiness

- Command: `make provider-lab-cisco-console-ethernet-readiness`
- Result: timed out after the command timeout window.
- Current status: no fresh identity/status payload from this pass.

### NetApp Console

- Commands:
  - `make provider-lab-netapp-console-autodiscovery`
  - `make provider-lab-netapp-console-read-state`
- Result: completed, blocked.
- Fresh artifacts:
  - `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
  - `artifacts/codex-runs/netapp-console-state-report.md`
- Current state: serial candidates were discovered, but no valid NetApp prompt, boot state, or login flow was detected.
- Selected candidate in this run: Prolific USB serial candidate at 9600 baud.
- Important detail: the Microchip MCP2221 path was detected but appeared in use during this sweep.

### ESXi Readiness

- Command: `make provider-lab-esxi-install-readiness`
- Result: blocked.
- Fresh artifact: `artifacts/codex-runs/esxi-install-readiness-report.md`
- Current evidence: DL360 Gen10 Plus reachable through iLO inventory, power on, health OK, virtual media supported, one-time boot supported, BIOS available.
- Blocker: RAID validation after reset must succeed before ESXi install readiness.

### Firmware

- Commands:
  - `make provider-lab-firmware-inventory`
  - `make provider-lab-firmware-compliance`
- Result: inventory completed with warnings; compliance blocked.
- Fresh artifacts:
  - `artifacts/codex-runs/firmware-inventory-report.md`
  - `artifacts/codex-runs/firmware-compliance-report.md`
- Current blockers:
  - iLO firmware current version unknown; baseline requires 3.19.
  - Cisco IOS XE version unknown; baseline requires 17.9.
- Not configured yet:
  - NetApp ONTAP, disk, shelf, and SP/BMC firmware inventory await live setup validation.

### Build Verification

- Command: `make provider-lab-build-verification`
- Result: blocked.
- Fresh artifact: `artifacts/codex-runs/build-verification-current-state-report.md`
- Current blockers:
  - iLO Redfish and XML fallback required ports not reachable in current build verification.
  - NetApp cluster management REST/SSH not reachable.
  - Provider environment inputs still need alignment with active setup `TDC-LAB`.
  - Cisco and ESXi management checks remain blocked until configured/confirmed.

### Toolchain

- Command: `make provider-lab-toolchain-check`
- Result: warning.
- Fresh artifact: `artifacts/codex-runs/toolchain-availability-report.md`
- Required missing: none.
- Optional missing: `netmiko`, `ansible`, `cisco.ios` collection, `govc`, `ilorest`, `netapp-ontap`, `pyATS/Genie`.

### Workflow Registry

- API checked: `/api/v1/workflows/actions`
- Current count: 72 actions across 9 stages.
- Current availability snapshot: 70 actions are manual/runnable by availability, 2 are blocked or gated by trace/blocker classification.

## Hardware Inventory Status

- Active setup: `TDC-LAB`
- Active subnet: `10.10.8.0/24`
- Rows shown: 10
- Rows: Cisco switch, HPE iLO, DL360 server, Smart Array / RAID, ESXi host, NetApp controller, NetApp cluster, UPS, backup storage, utility VM.
- Current table state: 10 rows are present, with no ready rows yet because most live discovery is blocked, stale, or not checked for the active setup.
- Notable saved values:
  - iLO: `10.10.8.200`
  - Server NIC: `10.10.8.201`
  - ESXi: `10.10.8.202`
  - Cisco: `10.10.8.203`
  - Control host: `10.10.8.5`
  - NetApp cluster management: `10.10.8.45`

## Screenshot Artifacts

- `artifacts/screenshots/product-cleanup-dashboard.png`
- `artifacts/screenshots/product-cleanup-hardware-list.png`
- `artifacts/screenshots/product-cleanup-edit-config.png`
- `artifacts/screenshots/product-cleanup-actions-dropdown.png`
- `artifacts/screenshots/product-cleanup-netapp.png`
- `artifacts/screenshots/product-cleanup-firmware-upgrades.png`
- `artifacts/screenshots/product-cleanup-validation-reports.png`

## Validation Run

- `npm run build`: passed; Vite reported the existing large chunk warning.
- `PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_lab_topology.py tests/test_api.py -k 'lab_profile or lab_profiles or profile'`: 12 passed, 39 deselected.
- `make lint`: passed; Vite reported the existing large chunk warning.
- `npx playwright test tests/safe-action-runner.spec.ts -g "uses merged navigation and dashboard lab setup selector"`: 1 passed.
- `make app-restart`: passed app-owned restart and its wrapper smoke test, 3 passed.

## Remaining Clutter

- Dashboard still carries the VM request workflow (`New VM`, workflow queue, preview execution). This may be useful for the broader portal, but it still competes with the lab-control cockpit goal.
- Control Center still shows high blocked-count badges from the report issue system; useful signal, but visually heavy.
- Some backend service/report internals still use `lab_profile` naming because the API/storage contract remains profile-based.
- Some older real-lab artifacts still reference stale/out-of-scope values; current operator views now favor active setup and fresh checks, but reports still include historical evidence when expanded.

## Skill Improvement Review

- The Lab Builder skills matched the work well: runtime state, UX simplification, hardware run safety, reports, and toolchain readiness all applied.
- Reusable improvement: add a short skill reference for "operator wording cleanup" that maps backend profile/demo/dry-run terms to operator-facing lab setup/preview/test mode language.
- Reusable improvement: add a hardware inventory verification checklist that pairs each row with expected live source, saved setup fallback, and proof artifact.
