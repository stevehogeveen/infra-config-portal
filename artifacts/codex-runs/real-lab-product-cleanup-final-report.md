# Real-Lab Product Cleanup Final Report

- Completed: 2026-06-10 16:22:22 EDT
- Repo: `/home/administrator/infra-config-portal`
- Safety: read-only/status real-lab checks only; credentials remained redacted
- App URL after restart: `http://127.0.0.1:5173`

## What Changed

- Added one top-level `Edit Config` button and drawer for the active lab setup.
- Changed operator wording from `Lab Profile` to `Lab Setup` while keeping backend profile behavior.
- Added a compact `Hardware` page with a spreadsheet-like inventory table and 10 equipment rows.
- Added per-row `Actions / Configs` dropdowns with customization options and collapsed proof.
- Cleaned control sections so reports/evidence stay collapsed and the top view focuses on firmware status, access, saved config, actions, and proof.
- Kept `Firmware Upgrades` and `Validation & Reports` as the operator buckets, with detailed reports behind expansion.
- Added `block_legacy_protocols` as a saved lab setup feature in backend schema, topology normalization, frontend types, and UI payloads.

## Mock Or Redundant UI Reduced

- Removed visible top-level `Settings / Lab Profile` navigation.
- Redirected the old provider page flow into the new `Hardware` cockpit list.
- Replaced visible `mock`, `test fixture`, `dry-run`, and `global profile` terms in operator views with `Test Mode`, `preview`, and `lab setup` language.
- Hid action catalog/report-heavy content from normal operator control pages unless Advanced mode or collapsed evidence is opened.

## Real Checks Run

- iLO reachability: passed via fallback/control-access DHCP candidate; active setup candidate timed out or filtered.
- Cisco console/ethernet readiness: timed out; no fresh identity payload.
- NetApp console autodiscovery/read-state: blocked; serial candidates found, no valid NetApp prompt/state detected.
- ESXi install readiness: blocked by required RAID validation after reset.
- Firmware inventory/compliance: inventory warning, compliance blocked by unknown iLO and Cisco firmware versions.
- Build verification/current state: blocked by iLO required ports, NetApp REST/SSH reachability, stale provider env mismatch with `TDC-LAB`, and unconfirmed Cisco/ESXi readiness.
- Toolchain: warning; required missing none, optional provider tools missing.
- Workflow registry: 72 actions across 9 stages.

## Hardware Inventory Status

- Active lab setup: `TDC-LAB`, subnet `10.10.8.0/24`.
- Table rows: Cisco switch, HPE iLO, DL360 server, Smart Array / RAID, ESXi host, NetApp controller, NetApp cluster, UPS, backup storage, utility VM.
- Current cockpit status: all 10 rows are present, but none are marked ready yet because live discovery is blocked, stale, or not checked against the active setup.

## Screenshots Captured

- `artifacts/screenshots/product-cleanup-dashboard.png`
- `artifacts/screenshots/product-cleanup-hardware-list.png`
- `artifacts/screenshots/product-cleanup-edit-config.png`
- `artifacts/screenshots/product-cleanup-actions-dropdown.png`
- `artifacts/screenshots/product-cleanup-netapp.png`
- `artifacts/screenshots/product-cleanup-firmware-upgrades.png`
- `artifacts/screenshots/product-cleanup-validation-reports.png`

## Tests Run

- `npm run build`: passed.
- `PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_lab_topology.py tests/test_api.py -k 'lab_profile or lab_profiles or profile'`: 12 passed, 39 deselected.
- `make lint`: passed.
- `npx playwright test tests/safe-action-runner.spec.ts -g "uses merged navigation and dashboard lab setup selector"`: 1 passed.
- `make app-restart`: wrapper smoke test passed, 3 tests.

## Remaining Clutter

- Dashboard still includes the VM request workflow and `New VM`; it is outside the lab-hardware cockpit lane but still visible.
- Sidebar/report badges can still become visually heavy when report-center issue counts spike.
- Backend/report internals still use `lab_profile` as an implementation contract.
- Expanded reports still expose historical artifacts and stale evidence, though normal operator pages now keep them collapsed.

## Next Best Step

Align the active saved setup with the physical lab or switch the active setup to the 192.168.1.x lab values, then rerun iLO inventory and NetApp console discovery so the hardware table can move from saved/planned values to verified live state.
