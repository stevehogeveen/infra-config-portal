# Grand Operation Stage 0 Preflight Report

Generated: 2026-06-10T18:10:17-04:00

## Scope

- Workspace: `/home/administrator/infra-config-portal`
- Reference app inspected read-only: `/home/administrator/lab-builder`
- Run type: real-lab grand operation
- Provider mode: `local-lab-readwrite`
- Git staging/commit/push: not performed
- Secret handling: no credential values printed or copied into this report

## Instructions And Skills

- `AGENTS.md` UTF-8 validation: passed.
- Root `AGENTS.md` and nested `app/AGENTS.md` were read.
- Applied skills:
  - `lab-builder-skill-steward`
  - `lab-builder-real-runtime`
  - `lab-builder-hardware-run`
  - `lab-builder-toolchain`
  - `lab-builder-report-remediation`
  - `lab-builder-ux`
  - `lab-builder-product-craft`
  - `lab-builder-dual-app-architecture`
  - memory procedure `ilo-real-lab-validation`

## Git Status

Fresh `git status --short --untracked-files=all` showed only pre-existing untracked AGENTS-related files:

```text
?? AGENTS.md.binary-broken.20260610-140429
?? AGENTS1.md
```

No files were staged, committed, or pushed.

## Local Real-Lab Configuration

- `.env.local.real-lab`: exists.
- `.env.local.real-lab`: ignored by Git.
- `.env.local.real-lab` mode/owner: `600`, `administrator`.
- Credential values were not inspected or printed.

## Active Lab Profile

Initial app state selected an older saved profile:

- Previous active profile: `lab-66160b5e59bc`
- Previous subnet: `10.10.8.0/24`

For this run, the saved high-address local lab profile was activated and applied to non-secret runtime IP keys:

- Active profile: `lab-225b7f90c0c1`
- Active profile name: `Screenshot High /24 20260610152354`
- Subnet: `192.168.1.0/24`
- iLO: `192.168.1.201`
- Server embedded NIC: `192.168.1.202`
- ESXi: `192.168.1.203`
- Cisco management: `192.168.1.204`
- Control/Ansible host: `192.168.1.205`
- NetApp controller A SP: `192.168.1.210`
- NetApp controller B SP: `192.168.1.211`
- NetApp cluster management: `192.168.1.220`
- NetApp node A management: `192.168.1.221`
- NetApp node B management: `192.168.1.222`
- NetApp SVM management: `192.168.1.223`
- NetApp NFS LIFs: `192.168.1.230`, `192.168.1.231`
- NetApp iSCSI LIFs: `192.168.1.240`, `192.168.1.241`, `192.168.1.242`, `192.168.1.243`

Runtime keys updated by the app profile service:

```text
ANSIBLE_CISCO_HOST
ANSIBLE_CONTROL_HOST
CISCO_TARGET_IP
ESXI_TEST_HOST
ILO_TEST_HOST
LAB_GATEWAY
LAB_SUBNET_CIDR
NETAPP_CLUSTER_MGMT_IP
NETAPP_CONTROLLER_A_SP
NETAPP_CONTROLLER_B_SP
NETAPP_ISCSI_LIFS
NETAPP_NFS_LIFS
NETAPP_NODE_A_MGMT_IP
NETAPP_NODE_B_MGMT_IP
NETAPP_SVM_MGMT_IP
SERVER_EMBEDDED_NIC_IP
```

Runtime key removed by the app profile service:

```text
LAB_DNS_SERVERS
```

Fresh API verification after app restart:

- Frontend: `http://127.0.0.1:5173/` returned HTTP 200.
- Backend health: `http://127.0.0.1:8001/health` returned HTTP 200.
- `/api/v1/lab/profiles` returned the `192.168.1.0/24` profile with `mismatch_count=0`.
- `/api/v1/settings/provider-mode` returned `current_mode=local-lab-readwrite`, `desired_mode=local-lab-readwrite`, `pending_restart=false`.
- `/api/v1/control/actions` returned `provider_mode=local-lab-readwrite` and sections: `lab-profile`, `cisco`, `ilo`, `raid`, `esxi`, `netapp`, `firmware-upgrade`, `verification`, `reports`.

Provider status is correctly not treated as live until fresh checks run:

| Provider | Status | Source | Freshness | Recheck |
| --- | --- | --- | --- | --- |
| iLO Redfish | ready | not_checked | unknown | `make provider-lab-ilo-reachability` |
| Cisco console | ready | not_checked | unknown | `make provider-lab-cisco-console-ethernet-readiness` |
| Cisco Ansible | awaiting-bootstrap | not_checked | unknown | `make provider-lab-cisco-console-ethernet-readiness` |
| ESXi readonly | planned-target | not_checked | unknown | `make provider-lab-esxi-install-readiness` |
| NetApp ONTAP | blocked | not_checked | unknown | `make provider-lab-netapp-live-state` |

## App Startup

`make app-start` ran the mock lifecycle smoke before startup:

```text
tests/test_smoke_vm_lifecycle.py: 3 passed
```

Current local app URLs:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8001`
- API docs: `http://127.0.0.1:8001/docs`

## Lab Builder Reference Ideas

Useful ideas inspected read-only from `/home/administrator/lab-builder`:

- Keep the operator workflow explicit: configuration, setup pages, preview/check actions, Run Center execution, reports/history/artifacts.
- Use the durable sequence: `Context -> Targets -> Credentials -> Current State -> Preflight -> Plan -> Execute -> Monitor -> Evidence -> Next Step`.
- Keep real execution confirmation-gated, with preview first and typed/checkbox confirmations for apply operations.
- Treat desired intent separately from live discovery; always discover immediately before apply.
- For failures, produce structured technician diagnostics: what was intended, what was discovered, what options existed, why it blocked, and what to do next.
- For ESXi rebuilds, verify base ISO, served URL, virtual media insertion/ejection, one-time boot options, power transition, and management reachability.
- Keep local media and generated artifacts under ignored local paths.
- Preserve secret-safe behavior: blank/password-preserve UI semantics and redacted reports.
- Keep evidence and raw output in reports/debug bundles rather than crowding the main operator surface.

## Stage 0 Result

Stage 0 passed with one local profile correction:

- The active lab profile was changed from the stale `10.10.8.0/24` profile to the saved `192.168.1.0/24` profile.
- The app was restarted and verified reachable.
- Provider states remain not-current until Stage 2+ live checks run.

Next action: Stage 1 media inventory.
