# Safe Read-Only Action Runner Audit

Date: 2026-06-09

Scope: `/home/administrator/infra-config-portal`

Skills used: `lab-builder-skill-steward`, `lab-builder-real-runtime`,
`lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-hardware-run`,
`lab-builder-report-remediation`, `lab-builder-toolchain`, and
`lab-builder-dual-app-architecture`.

## Safety Posture

- No destructive workflow was run during this audit.
- No write, reset, install, apply, bootstrap, or upgrade action is UI-runnable
  in this pass.
- Mock/test state remains separate from current real-lab state. New UI run
  results are stored as `source_type=live_probe`, `freshness=current`, and
  `not_mock=true`.
- Historical artifacts remain evidence only. They do not override a newer
  workflow action run trace.
- Secrets are not printed. Runner output summaries pass through sensitive-value
  and password/token redaction before being saved.

## UI-Runnable Allowlist

These registry actions are safe to expose as UI run controls now because their
registry mode is `read_only` or `report_only`, they require no destructive or
write confirmation, and their command/API endpoint exactly matches the runner
allowlist.

| Registry action | Mode | Runner | UI label |
| --- | --- | --- | --- |
| `cisco.discover-console` | `read_only` | `make provider-lab-serial-console-discovery` | Run Check |
| `cisco.privilege-check` | `read_only` | `make provider-lab-cisco-privilege-check` | Run Check |
| `cisco.firmware-inventory` | `read_only` | `make provider-lab-firmware-cisco-inventory` | Check Firmware |
| `cisco.validate-ssh-scp` | `read_only` | `make provider-lab-cisco-console-ethernet-readiness` | Refresh Status |
| `ilo.reachability` | `read_only` | `make provider-lab-ilo-reachability` | Run Check |
| `ilo.auth` | `read_only` | `make provider-lab-ilo-authentication` | Run Check |
| `ilo.inventory` | `read_only` | `make provider-lab-ilo-inventory` | Refresh Status |
| `esxi.readiness` | `read_only` | `make provider-lab-esxi-install-readiness` | Refresh Status |
| `netapp.serial-console-discovery` | `read_only` | `make provider-lab-serial-console-discovery` | Run Check |
| `netapp.console-autodiscovery` | `read_only` | `make provider-lab-netapp-console-autodiscovery` | Run Check |
| `netapp.console-read-state` | `read_only` | `make provider-lab-netapp-console-read-state` | Read Console State |
| `netapp.nfs-vcenter-readiness` | `read_only` | `make provider-lab-netapp-nfs-vcenter-readiness` | Refresh Status |
| `firmware.compliance-check` | `read_only` | `make provider-lab-firmware-compliance` | Check Firmware |
| `build-verification.run-full` | `read_only` | `make provider-lab-build-verification` | Run Verification |
| `build-verification.toolchain-check` | `read_only` | `make provider-lab-toolchain-check` | Check Toolchain |
| `lab-profile.view-active` | `read_only` | `GET /api/v1/lab/profiles` | Refresh Status |
| `reports.issue-center` | `report_only` | `GET /api/v1/reports/issues` | Refresh Status |
| `reports.summary` | `report_only` | `GET /api/v1/reports/summary` | Refresh Status |

## Explicitly Blocked From UI Run

These actions stay command-only or guarded. The runner refuses them before any
subprocess or API action starts.

| Registry action | Mode | Reason |
| --- | --- | --- |
| `cisco.apply-bootstrap` | `write` | Cisco bootstrap apply is a write workflow. |
| `cisco.save-config` | `write` | Saves switch configuration. |
| `cisco.reload-if-needed` | `destructive` | Reload/reset path requires guarded workflow. |
| `cisco.reclaim-console` | `write` | Console reclaim is operationally write-capable. |
| `commander.reclaim-serial-port` | `write` | Serial reclaim is write-capable. |
| `commander.ignore-cached-artifact` | `write` | Alters evidence selection behavior. |
| `ilo.virtual-media-insert` | `write` | iLO virtual media insert writes state. |
| `ilo.one-time-boot` | `write` | iLO boot settings write state. |
| `ilo.reset-server` | `destructive` | Server reset is destructive/power-affecting. |
| `raid.apply` | `destructive` | RAID apply can change storage layout. |
| `raid.reset-commit` | `destructive` | Reset/commit path is destructive. |
| `esxi.virtual-media-insert` | `write` | Virtual media insert writes iLO state. |
| `esxi.one-time-boot` | `write` | One-time boot changes server boot state. |
| `esxi.rebuild-install` | `destructive` | ESXi rebuild/install is destructive. |
| `esxi.kickstart-generation` | `write` | Generates install material for a write workflow. |
| `firmware.create-waiver` | `write` | Waiver creation is a write action. |
| `firmware.upgrade-plan` | `upgrade` | Upgrade lane is not enabled for UI runs. |
| `firmware.upgrade-apply-placeholder` | `upgrade` | Firmware upgrade apply is not enabled. |

## Read-Only But Not Yet UI-Runnable

The following actions remain copy-only because they are not in the runner
allowlist yet, or their command shape needs a more specific safety review.

- `lab-profile.validate-ip-profile`
- `firmware.inventory`
- `firmware.package-inventory`
- `firmware.waiver-check`
- `ilo.firmware-inventory`
- `raid.debug`
- `raid.discovery`
- `raid.pending-check`
- `raid.plan`
- `raid.validate`
- `esxi.installer-boot-detection`
- `esxi.iso-media-check`
- `esxi.management-readiness`
- `esxi.management-validation`
- `esxi.ssh-api-check`
- `netapp.live-state`
- `netapp.setup-preview`
- `netapp.validate-setup`
- `build-verification.export-certification-report`
- `build-verification.live-status`
- `build-verification.run-scoped`
- `commander.force-live-discovery`
- `commander.run-live-check`

## Runner Guardrails

The execution layer must keep these invariants:

1. Look up the action from the workflow registry before execution.
2. Refuse any mode other than `read_only` or `report_only`.
3. Refuse any action with required confirmations.
4. Execute only the exact allowlisted command tuple or API endpoint.
5. Capture and redact stdout/stderr summaries before saving.
6. Save a run trace under
   `artifacts/codex-runs/workflow-action-runs/`.
7. Return current run evidence without treating old artifacts as fresh state.
