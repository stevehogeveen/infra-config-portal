# NetApp ONTAP Upgrade Apply Report

- Checked at: `2026-06-11T02:39:19.656981+00:00`
- Status: `blocked`
- Apply enabled: `False`
- Upgrade writes attempted: `False`

## Required Flags
- `PROVIDER_MODE=local-lab-readwrite`
- `NETAPP_ONTAP_UPGRADE_APPLY=true`
- `NETAPP_ONTAP_UPGRADE_CONFIRM="UPGRADE ONTAP"`

## Blockers
- NetApp cluster management is not configured/reachable yet.
- NetApp API access values are missing; keep values in .env.local.real-lab.
- Current ONTAP version is unknown until ONTAP/API/CLI discovery can run.
- Pre-upgrade validation has not passed.
- Manual Upgrade Advisor/Health Checker plan is not attached.
- NETAPP_ONTAP_UPGRADE_APPLY=true is required.
- NETAPP_ONTAP_UPGRADE_CONFIRM="UPGRADE ONTAP" is required.
- Pre-upgrade validation has not passed and no explicit waiver is present.
- Current ONTAP version is unknown.

## Safety
- No secrets are written to this report.
