# Grand Operation Stage 7 - NetApp Setup Report

Checked at: 2026-06-10T23:09:38Z
Scope: local real lab, NetApp targets `192.168.1.210-192.168.1.223`, NFS LIFs `192.168.1.230`, `192.168.1.231`

## Result

- Status: blocked before NetApp setup writes.
- Console detection: successful enough to find a NetApp login prompt on `/dev/ttyACM0` at `115200`.
- Earlier autodiscovery selected the stable MCP2221 by-id path, but that path returned unreadable text during this run.
- Cluster management REST at `192.168.1.220`: not reachable.
- NetApp API/console credentials: missing from local ignored configuration; no secrets were printed or written.
- Detected console state: `login_required`, not `cluster_setup_wizard`.
- NetApp setup apply: invoked with required non-secret confirmation flags and correctly refused before serial or ONTAP writes.
- ONTAP upgrade: inventory, plan, and validation are blocked because cluster/API state is unavailable.
- NFS/vCenter readiness: blocked because NetApp is not configured and vCenter/govc target is not configured.

## Current Planned Topology

- Controller A SP: `192.168.1.210`
- Controller B SP: `192.168.1.211`
- Cluster management: `192.168.1.220`
- Node A management: `192.168.1.221`
- Node B management: `192.168.1.222`
- SVM management: `192.168.1.223`
- NFS LIFs: `192.168.1.230`, `192.168.1.231`
- NFS volume: `esxi_datastore_01`
- Mount path: `/esxi_datastore_01`
- Export policy: `esxi_nfs_policy`
- Export client match: `192.168.1.0/24`

## Setup Intent Blockers

- Console state is `login_required`; setup apply only supports cluster/node setup wizard states.
- Required non-secret setup intent fields are missing:
  - `cluster_name`
  - `node_a_name`
  - `node_b_name`
  - `svm_name`
  - `dns_servers`
  - `ntp_servers`
  - `search_domains`
  - `admin_access_source`
- NetApp console/API credentials are missing locally, so guarded login and read-only ONTAP state identification were skipped.

## Upgrade Status

- Current ONTAP version: unknown.
- Target ONTAP version from media planning: `9.17.1`.
- Local ONTAP packages are available in `artifacts/Media`, but upgrade validation is blocked until cluster management is configured/reachable, API access is available, a supported upgrade path is confirmed, and the manual Upgrade Advisor/Health Checker plan is attached.
- No package upload, image validation, controller reboot, takeover/giveback, or ONTAP upgrade command was run.

## App/Product Fix From This Stage

- `app/backend/app/services/netapp_setup_intent.py`: setup apply reports now expose missing setup intent fields at top level and include a remediation section in the operator report.
- `app/backend/tests/test_netapp_setup_upgrade_center.py`: added regression coverage for missing intent fields in setup apply output.

## Validation

- `make provider-lab-netapp-console-autodiscovery`: blocked; by-id MCP2221 candidate at 115200 produced unreadable text.
- `make provider-lab-netapp-console-read-state`: ready; `/dev/ttyACM0` at 115200 produced a NetApp login prompt.
- `make provider-lab-netapp-console-login-state`: blocked; credentials missing, login skipped.
- `make provider-lab-netapp-live-state`: blocked; cluster REST unreachable and API access missing.
- `make provider-lab-netapp-validate-setup`: blocked by live-state evidence.
- `make provider-lab-netapp-setup-baseline`: blocked; console state is `login_required`.
- `make provider-lab-netapp-setup-plan`: blocked; setup intent incomplete.
- `make provider-lab-netapp-setup-preview`: blocked; setup intent incomplete.
- `NETAPP_SETUP_APPLY=true NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP" NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true make provider-lab-netapp-setup-apply`: blocked before writes, as expected.
- `make provider-lab-netapp-post-setup-validation`: blocked; cluster REST unreachable and API access missing.
- `make provider-lab-netapp-ontap-upgrade-inventory`: not configured yet.
- `make provider-lab-netapp-ontap-upgrade-plan`: blocked.
- `make provider-lab-netapp-ontap-upgrade-validate`: blocked.
- Focused NetApp tests passed; Ruff checks passed for changed NetApp files.

## Evidence

- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-console-login-state-report.md`
- `artifacts/codex-runs/netapp-live-state-report.md`
- `artifacts/codex-runs/netapp-setup-upgrade-baseline-report.md`
- `artifacts/codex-runs/netapp-setup-plan-report.md`
- `artifacts/codex-runs/netapp-setup-preview-report.md`
- `artifacts/codex-runs/netapp-cluster-setup-apply-report.md`
- `artifacts/codex-runs/netapp-post-setup-validation-report.md`
- `artifacts/codex-runs/netapp-upgrade-inventory-report.md`
- `artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md`
- `artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md`
- `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`

## Exact Next Action

Provide local-only NetApp console/API credentials in `.env.local.real-lab`, set the non-secret NetApp setup intent fields, then rerun `make provider-lab-netapp-console-login-state` followed by `make provider-lab-netapp-setup-preview`.
