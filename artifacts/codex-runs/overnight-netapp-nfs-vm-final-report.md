# Overnight NetApp NFS VM Final Report

Generated: 2026-06-10

## Summary

The overnight run completed the guarded workflow implementation and validation work, but did not perform physical NetApp cluster setup, NFS storage creation, datastore mount, VM deployment, or firmware/software upgrades. The live blockers are credential/access and readiness blockers, not mock or stale blockers.

## Configured

- Implemented a guarded NetApp NFS setup lane for preview, apply, and validation.
- Implemented a guarded direct ESXi OVF VM deployment lane with datastore selection, defaulting to `netapp_nfs_ds01`.
- Added API routes, Control Center actions, workflow registry entries, frontend API helpers, and NetApp UI controls for the new lanes.
- Filled non-secret NetApp setup intent defaults for the active lab:
  - Cluster: `lab-netapp-cluster`
  - Nodes: `lab-netapp-node-a`, `lab-netapp-node-b`
  - SVM: `esxi_svm`
  - NFS volume: `esxi_datastore_01`
  - Mount path: `/esxi_datastore_01`
  - Export policy: `esxi_nfs_policy`
  - Export client match: `192.168.1.0/24`
  - Preferred NFS LIF: `192.168.1.230`
  - Fallback NFS LIF: `192.168.1.231`

## Upgraded

- No firmware or software upgrade was applied.
- ONTAP upgrade apply was safely refused because live ONTAP discovery, current version, Advisor validation, credentials, and confirmation gates were not complete.
- HPE, Cisco, ESXi, NetApp, and vCenter upgrade work remained in inventory/plan/readiness state only.

## Validated

- `AGENTS.md` is valid UTF-8.
- `.env.local.real-lab` is present, ignored, and not staged.
- iLO at `192.168.1.201` is reachable and read-only inventory succeeded.
- ESXi at `192.168.1.203` is installed and reachable on HTTPS/SSH.
- NetApp console autodiscovery found the MCP2221 serial path at 115200 baud, but the console state is `login_required`.
- NetApp cluster REST at `192.168.1.220` was not reachable during the run.
- NetApp setup preview remained blocked by missing NetApp access and `admin_access_source`.
- NetApp NFS setup preview/apply/validate remained blocked by missing live NetApp configured state and API access.
- ESXi datastore and VM deploy validation confirmed `netapp_nfs_ds01` is not visible yet.
- VCSA media was located, but vCenter/govc target configuration is not present.
- App usability screenshots were saved under `artifacts/screenshots/`.

## NetApp Cluster Status

NetApp cluster setup is not configured yet. The console is reachable only to a login-required state, and ONTAP REST is unreachable at the cluster management address.

## NFS Status

NFS is not configured yet on NetApp. The repo now has a guarded NFS setup workflow ready to create or validate the SVM, NFS service, LIFs, volume, export policy, and export rules once NetApp access is available.

## ESXi Datastore Status

ESXi does not have `netapp_nfs_ds01` mounted. The datastore mount workflow remained blocked because NetApp NFS is not ready and the datastore is not visible to direct ESXi govc.

## OVF VM Deployment Status

No OVF VM was deployed onto NetApp storage. The direct ESXi OVF deployment lane is implemented and validates that the target datastore exists before import. Apply remained blocked because `netapp_nfs_ds01` is not mounted.

## vCenter Status

VCSA ISO media is available under `artifacts/Media`, but vCenter is not configured in the local lab state. vCenter readiness and datastore planning remain blocked until vCenter host/credentials and target deployment values are configured.

## Firmware And Upgrade Status

- iLO inventory identified HPE ProLiant DL360 Gen10, iLO 5 v3.19, BIOS U32 v3.30, and Smart Array P408i-a firmware 1.98.
- ESXi is VMware ESXi 8.0.3 build 24859861.
- Cisco console readiness is login-gated; Cisco firmware inventory did not complete cleanly and was stopped after it hung.
- ONTAP current version and cluster identity are unknown because live ONTAP access is not available.
- No upgrade met the required gates for safe apply.

## App Usability Changes

- Added NetApp NFS setup controls and status surfaces.
- Added guarded ESXi VM deployment workflow support with datastore targeting.
- Added control action allowlist coverage for the new guarded lanes.
- Kept apply actions disabled unless explicit local-lab-readwrite mode and confirmation variables are present.
- Saved screenshots for dashboard, hardware, NetApp, firmware upgrades, validation reports, and VM deployment.

## Validation Commands

- Focused backend tests: passed, 31 tests.
- `make lint`: passed.
- `make test`: passed, 387 backend tests plus frontend build.
- `git diff --cached --check`: passed before commit.
- Staged high-confidence secret scan: no matches before commit.
- Forbidden staged path check for `.env.local.real-lab`, logs, PID files, and media: no matches before commit.

## Commits And Pushes

- Commit `fb6c7a1` (`Complete NetApp NFS setup workflow and validation`) was pushed to `origin/main`.
- Commit `49c8bbc` (`Add overnight NetApp NFS VM final report`) was pushed to `origin/main`.

## Remaining Blockers

- NetApp console/API credentials are not configured for the run.
- NetApp console state is `login_required`.
- NetApp cluster REST at `192.168.1.220` is unreachable.
- NetApp setup intent still needs `admin_access_source`.
- `netapp_nfs_ds01` is not mounted on ESXi.
- vCenter/govc target configuration is missing.
- Cisco console credentials are not configured for firmware inventory.
- Firmware/software upgrades need known current versions, known target packages, validated upgrade paths, credentials, confirmation gates, and progress/reporting support before apply.

## Exact Next Morning Action

Configure the missing NetApp local-lab access without printing secrets: add `NETAPP_CONSOLE_USERNAME`, `NETAPP_CONSOLE_PASSWORD`, `NETAPP_API_USERNAME`, and `NETAPP_API_PASSWORD` to `.env.local.real-lab`, set the non-secret `NETAPP_ADMIN_ACCESS_SOURCE`, then rerun `make provider-lab-netapp-live-state` and `make provider-lab-netapp-setup-preview`. Do not run setup or NFS apply until the console/API state is understood and the explicit confirmation gates are set.
