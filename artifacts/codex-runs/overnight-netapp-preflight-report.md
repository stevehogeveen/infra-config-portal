# Overnight NetApp NFS VM Preflight Report

Checked at: 2026-06-10T22:07:55-04:00

## Scope

- Repo: `/home/administrator/infra-config-portal`
- Branch: `main`
- Head: `c1b3dea Validate real lab foundation and direct ESXi VM deployment`
- Remote state: `main...origin/main`
- Real-lab target: local lab `192.168.1.0/24`
- Storage instruction: NetApp NFS only; iSCSI is out of scope for this operation.
- Skills used: `lab-builder-skill-steward`, `lab-builder-real-runtime`, `lab-builder-hardware-run`, `lab-builder-toolchain`, `lab-builder-report-remediation`, `lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-dual-app-architecture`.

## Safety Preflight

- `AGENTS.md` UTF-8 validation: passed.
- `.env.local.real-lab`: present, ignored by Git, mode `600`.
- `artifacts/Media`: ignored by Git.
- `artifacts/real-lab`: ignored by Git.
- Source tree status for `app`, `README.md`, `Makefile`, `scripts`, `config`, and `AGENTS.md`: clean.
- Worktree status: dirty due to pre-existing generated run artifacts and local runtime files under `artifacts/codex-runs/`, plus ignored media/runtime evidence. These are treated as historical evidence unless refreshed by this run.
- Untracked terminal/log/runtime files are not safe to commit.

## Local Credential And Gate Status

Only configured/missing status was checked. Values were not printed.

- Real hardware acknowledgements: configured.
- Closed-loop/read-only gates: configured.
- Apply/target gates: missing.
- iLO host and credential references: configured.
- Cisco target and credential references: configured.
- ESXi host and credential references: configured.
- NetApp target addresses: configured.
- NetApp API credential references: missing (`NETAPP_API_USERNAME`, `NETAPP_API_PASSWORD`).
- NetApp NFS intent values in local env: missing (`NETAPP_STORAGE_PROTOCOL`, `NETAPP_NFS_VOLUME`, `NETAPP_NFS_EXPORT_POLICY`, `NETAPP_NFS_MOUNT_PATH`, `NETAPP_NFS_DATASTORE_NAME`, `NETAPP_NFS_CLIENT_MATCH`).
- NetApp guarded setup apply gates: missing (`NETAPP_SETUP_APPLY`, `NETAPP_SETUP_CONFIRM`, `NETAPP_SETUP_ALLOW_CLUSTER_CREATE`).
- vCenter/govc target and credential references: missing.

## Available Media

- OVF template: `artifacts/Media/OVF_Templates/DepOps_W2K22_Template_VMware7.0_Feb2025-1.0/DepOps_W2K22_Template_VMware7.0_Feb2025-v1.0.ovf`
- ESXi ISO media: ESXi 7.0.3 HPE Sep2024, ESXi 8.0.3 HPE Oct2025.
- vCenter media: `VMware-VCSA-all-8.0.3-24853646.iso`
- iLO firmware media: `ilo5_319.fwpkg`, `ilo6_176.fwpkg`
- Cisco IOS XE media: `cat9k_iosxe.17.15.05.SPA.bin`
- NetApp image media candidates: `9131P17_q_image.tgz`, `9141P14_q_image.tgz`, `9171_q_image.tgz`

## Stage 0 Result

Preflight passed for continuing read-only discovery, preview generation, UI/workflow implementation, and guarded readiness work. NetApp setup apply, ONTAP/NFS apply, vCenter work, and VM deployment to a NetApp datastore require fresh discovery plus their explicit credential and confirmation gates.
