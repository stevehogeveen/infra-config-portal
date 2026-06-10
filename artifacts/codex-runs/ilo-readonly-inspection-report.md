# iLO Read-only Inspection Report

Generated: 2026-06-10T18:55:02.371042+00:00
Scope: HPE iLO / DL360 read-only inspection for current TDC-LABv1 run.
Redaction: raw host addresses, serial values, UUIDs, and credentials are omitted.

## Summary

- Reachable: yes
- Selected source: `control_access_original_dhcp_ip`
- Active lab subnet: `10.10.8.0/24`
- iLO firmware: `iLO 5 v3.19`
- iLO model: `iLO 5`
- Server model: `ProLiant DL360 Gen10 Plus`
- BIOS version: `U46 v1.80 (07/05/2023)`
- Power state: `On`
- Overall health: system `OK`, rollup `OK`, chassis `OK`, controller `OK`
- Thermal summary available: `True`
- Power summary available: `True`

## Reachability Attempts

- candidate 1 (active_lab_profile): tcp_timeout_or_filtered, tcp_reachable=False, tcp_failure=timeout
- candidate 2 (control_access_original_dhcp_ip): redfish_root_available, tcp_reachable=True, tcp_failure=none

## RAID Visibility

- Visible: `True`
- Controller count: `1`
- Physical drive entries: `8`
- Logical drive count: `2`
- Controller: `HPE MR416i-a Gen10+` firmware `52.26.3-5379`

### Physical Drives

- Bay 0: HPE 960GB 22G SAS SSD, state=Enabled, health=OK, media=SSD, protocol=SAS, capacity=894.3 GiB
- Bay 1: HPE 960GB 22G SAS SSD, state=Enabled, health=OK, media=SSD, protocol=SAS, capacity=894.3 GiB
- Bay 2: HPE 960GB 22G SAS SSD, state=Enabled, health=OK, media=SSD, protocol=SAS, capacity=894.3 GiB
- Bay 3: HPE 960GB 22G SAS SSD, state=Enabled, health=OK, media=SSD, protocol=SAS, capacity=894.3 GiB
- Bay 4: HPE 960GB 22G SAS SSD, state=StandbySpare, health=OK, media=SSD, protocol=SAS, capacity=894.3 GiB
- Bay 64518: Empty Bay, state=Absent, health=OK, media=unknown, protocol=unknown, capacity=unknown GiB
- Bay 64520: Empty Bay, state=Absent, health=OK, media=unknown, protocol=unknown, capacity=unknown GiB
- Bay 64519: Empty Bay, state=Absent, health=OK, media=unknown, protocol=unknown, capacity=unknown GiB

### Logical Drives

- Data RAID 1 log: RAID1, 893.8 GiB, health=OK, members=2, spares=1
- OS RAID 1 logic: RAID1, 500.0 GiB, health=OK, members=2, spares=0

## Virtual Media State

- Inserted: `False`
- Connected via: `NotConnected`
- Image present: `False`

## Boot Override State

- Enabled: `Disabled`
- Mode: `UEFI`
- Target: `None`

## Failure Classification

- unreachable: active-profile candidate timed out before Redfish; first-access candidate succeeded.
- credentials missing: no.
- TLS/self-signed issue: no current blocker; local lab TLS verification is disabled for this read-only run.
- unsupported endpoint: `/redfish/v1/Systems/1/NetworkAdapters/` returned 404; not blocking; EthernetInterfaces and storage endpoints were available.
- stale report only: no; this report uses the latest current-run artifacts listed below.
- code/test bug: no current blocker; redaction classification handling has targeted test coverage.

## UI Update

- Added a plan-only visual drive assignment board for HPE RAID planning.
- Each discovered bay can be assigned as unused, a logical-volume member, or a dedicated spare.
- Empty/absent bays remain visible but disabled.
- No destructive apply path was enabled or changed.

## Evidence

- Reachability: `artifacts/real-lab/ilo-reachability-20260610T184329Z.json`
- Provider inventory: `artifacts/real-lab/provider-smoke-20260610T184525Z.json`
- HPE RAID discovery: `artifacts/codex-runs/hpe-raid-discovery-report.md`
- ESXi boot/virtual media: `artifacts/codex-runs/esxi-installer-boot-report.md`
- Redacted JSON: `artifacts/codex-runs/ilo-readonly-inspection-redacted.json`

## Commands / Tests Run

- `file -bi AGENTS.md`
- `iconv -f UTF-8 -t UTF-8 AGENTS.md >/dev/null`
- `make provider-lab-ilo-reachability`
- `make provider-lab-ilo-inventory`
- `make provider-lab-hpe-storage-discovery`
- `make provider-lab-esxi-detect-installer`
- `npm run build (app/frontend)`
- `.venv/bin/python -m pytest -q tests/test_provider_status_adapters.py::<10 targeted tests>`
- `git diff --check -- <touched HPE/iLO/frontend files>`

## Skill Improvement Review

- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-hardware-run, lab-builder-toolchain, lab-builder-report-remediation, lab-builder-ux, lab-builder-product-craft.
- Skills created or updated: none.
- Skill gaps found: none for this read-only iLO/storage/reporting pass.
