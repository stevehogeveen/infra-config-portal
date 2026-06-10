# NetApp Real-Run Readiness

This runbook prepares a real-lab NetApp readiness pass without performing real
ONTAP execution.

## Scope

Focus only on the NetApp setup and upgrade workflow. Do not run Cisco, iLO,
ESXi, OVF, or unrelated provider flows for this pass.

This is a readiness pass, not an ONTAP setup, datastore apply, or upgrade pass.

## Safety

- Treat `.env.local.real-lab` as bootstrap/profile input only. `NETAPP_CONFIGURED`
  is legacy/advanced context; live configured state is detected and persisted
  automatically.
- Keep provider mode mock by default.
- Use `PROVIDER_MODE=local-readonly` only for the explicit NetApp readiness
  command below.
- Do not perform real ONTAP config, firmware upgrade, takeover/giveback,
  reboot, wipe, storage provisioning, LIF creation, SSH, console command, SP
  API, vCenter datastore attach, ESXi datastore mount, or destructive action.
- The real-lab console discovery/read-state workflow opens local serial
  candidates only in explicit real-lab modes and sends newline and carriage
  return wake bytes only. It must not send Ctrl+C, Ctrl+Z, break,
  credentials, setup commands, boot menu selections, or ONTAP commands.
- Do not print or commit secrets.
- Do not commit `.env.local.real-lab` or anything under `artifacts/real-lab/`.

## Current NetApp Planning Convention

NetApp is part of the current `192.168.1.0/24` isolated lab profile. Keep
these as planned targets until ONTAP cluster management and credentials are
explicitly ready for a future read-only discovery stage.

- Controller A SP: `192.168.1.210`
- Controller B SP: `192.168.1.211`
- Cluster management: `192.168.1.220`
- Node A management/e0M: `192.168.1.221`
- Node B management/e0M: `192.168.1.222`
- SVM management: `192.168.1.223`
- NFS LIF default preview: `192.168.1.230,192.168.1.231`
- Future iSCSI LIF range: `192.168.1.240-192.168.1.243`

Only one NetApp management port is currently connected. Treat that as enough
for initial console/API bring-up only. Full HA, Controller B SP/node management,
SVM management, and NFS data-path validation remain incomplete until the
remaining management/data paths are connected and configured.

## Stale Address Note

Old `10.10.8.x` NetApp addresses are stale for the current
DL360/Cisco/ESXi/NetApp real-lab IP profile. Build Verification should flag
active `10.10.8.x` values as stale evidence instead of treating them as usable
targets.

## Command

From the repository root:

```bash
PROVIDER_MODE=local-readonly make netapp-real-readiness
```

The command writes redacted `netapp-readiness-*` JSON and Markdown reports
under ignored `artifacts/real-lab/`.

Read-only real-lab console and NFS/vCenter readiness targets:

```bash
make provider-lab-serial-console-discovery
make provider-lab-netapp-console-autodiscovery
make provider-lab-netapp-console-discovery
make provider-lab-netapp-console-read-state
make provider-lab-netapp-console-login-state
make provider-lab-netapp-live-state
make provider-lab-netapp-validate-setup
make provider-lab-netapp-nfs-vcenter-readiness
```

These commands save/update:

- `artifacts/codex-runs/serial-console-discovery-report.md`
- `artifacts/codex-runs/serial-console-discovery-redacted.json`
- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-autodiscovery-redacted.json`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-console-state-redacted.json`
- `artifacts/codex-runs/netapp-console-login-state-report.md`
- `artifacts/codex-runs/netapp-console-login-state-redacted.json`
- `artifacts/codex-runs/netapp-console-last-known-good-redacted.json`
- `artifacts/codex-runs/netapp-live-state-report.md`
- `artifacts/codex-runs/netapp-state-automanagement-report.md`
- `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`
- `artifacts/codex-runs/netapp-nfs-vcenter-readiness-redacted.json`

## Review Checklist

- Confirm the command prints `no_netapp_calls_made=true`.
- Confirm `.env.local.real-lab` is not required for discovered console port or
  configured-state tracking.
- Confirm planned targets use the current `192.168.1.210/.211/.220+` NetApp profile.
- Confirm planned targets are separate from current/discovered targets.
- Confirm current/discovered ONTAP API/storage targets remain separate from
  planned targets.
- Confirm console discovery reports the selected adapter/baud or the concrete
  blocker.
- Confirm discovered port, baud, confidence, last seen, and source are shown as
  automatic runtime state.
- Confirm configured state says verified by live check only after validation
  succeeds.
- Confirm setup readiness remains blocked until physical/console checks, ONTAP
  API configuration, and NFS/vCenter prerequisites are complete.
- Confirm upgrade readiness remains blocked until setup readiness and safe
  discovery prerequisites exist.
- Confirm NFS/vCenter readiness is preview-only and reports no apply control.
- Confirm artifacts do not contain passwords, tokens, raw configs, or secrets.

## Normal Gates

After any source changes, run:

```bash
python3 -m compileall app/backend/app
cd app && PROVIDER_MODE=mock make backend-test
cd app/frontend && PROVIDER_MODE=mock npm run build
git diff --check
PROVIDER_MODE=mock make lint
```
