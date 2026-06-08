# NetApp Lab Profile Plan

- Checked at: `2026-06-07T14:06:40Z`
- Provider mode for build verification: `local-lab-readwrite`
- NetApp readiness command: `PROVIDER_MODE=local-readonly make netapp-real-readiness`
- NetApp calls made: `false`

## Planned NetApp Targets

- Controller A SP: `192.168.1.206`
- Controller B SP: `192.168.1.207`
- Cluster management: `192.168.1.208`
- Node A management/e0M: `192.168.1.209`
- Node B management/e0M: `192.168.1.210`
- SVM management: `192.168.1.211`
- iSCSI LIFs: `192.168.1.212,192.168.1.213,192.168.1.214,192.168.1.215`

## Current Safety State

- `NETAPP_CONFIGURED=false`
- NetApp REST: `not_configured_yet`
- NetApp SSH: `not_configured_yet`
- Apply/setup/upgrade/reboot/wipe actions: disabled
- Current/discovered NetApp targets: not discovered

## Generated Evidence

- Build Verification report: `artifacts/codex-runs/build-verification-report.md`
- Lab IP profile report: `artifacts/codex-runs/lab-ip-profile-update-report.md`
- NetApp readiness report: `artifacts/real-lab/netapp-readiness-20260607T140640Z.md`

## Next Safe Step

Keep NetApp as planned/readiness-only until ONTAP cluster management is actually configured at `192.168.1.208`, credentials are stored only in `.env.local.real-lab`, and an explicit read-only NetApp discovery workflow is added.
