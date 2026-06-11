# Grand Operation Stage 9 - VM Deployment Report

Checked at: 2026-06-10T23:25:40Z
Scope: direct ESXi deployment to `192.168.1.203`

## Result

- Status: deployed and validated.
- Deployment method: direct `govc import.ovf` to ESXi, not vCenter.
- VM name: `grand-operation-test-vm`
- Template: `artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0.ovf`
- Disk source: `DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0-1.vmdk`, about 9.1 GB.
- Datastore: `datastore1`
- Network: `VM Network`
- Disk provisioning: `thin`
- Power state: `poweredOff`
- Guest type: Microsoft Windows Server 2022 (64-bit)
- vCPU/memory: 1 vCPU, 4096 MB
- Inventory path: `/ha-datacenter/vm/grand-operation-test-vm`

## Validation

- `govc import.spec` generated successfully.
- Import options were generated with VM name `grand-operation-test-vm`, `thin` disk provisioning, and `VM Network` mapping.
- `govc import.ovf` completed successfully.
- `govc vm.info grand-operation-test-vm` confirmed the VM is registered and powered off.
- `govc find / -type m` showed:
  - `/ha-datacenter/vm/win2022-01`
  - `/ha-datacenter/vm/grand-operation-test-vm`
- `govc datastore.info datastore1` after deployment showed VMFS datastore capacity `371.8 GB`, free `348.7 GB`.

## Caveats

- This deployment used direct ESXi access because vCenter is not configured and NetApp NFS datastore readiness is blocked by NetApp setup.
- The VM was not powered on; the stage requirement was to deploy one test VM and validate that it appears in ESXi/vCenter when practical.
- The app's built-in VM request lifecycle remains mock/provider-planning oriented for real deployment; real `govc import` is not yet represented as a guarded app lane.

## Evidence

- `artifacts/codex-runs/vm-deploy-import-spec-redacted.json`
- `artifacts/codex-runs/vm-deploy-import-options-redacted.json`
- `artifacts/codex-runs/vm-deploy-grand-operation-test-vm-info-redacted.json`
- `artifacts/codex-runs/vm-deploy-vm-inventory.txt`
- `artifacts/codex-runs/vm-deploy-datastore-info-redacted.json`

## Exact Next Action

Add a guarded real-lab VM deployment lane to the app that wraps the successful direct ESXi `govc import.ovf` pattern, with explicit datastore/network selection, power-on choice, and evidence capture.
