# NetApp ONTAP Upgrade Plan Report

- Checked at: `2026-06-10T00:37:11.764557+00:00`
- Status: `blocked`
- Current version: `unknown`
- Target version: `none`
- Package loaded: `False`
- Button state: `Disabled: NetApp not configured`
- Apply command: `NETAPP_ONTAP_UPGRADE_APPLY=true NETAPP_ONTAP_UPGRADE_CONFIRM="UPGRADE ONTAP" PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-ontap-upgrade-apply`

## Expected Commands / API Calls
- inventory: `cluster image package show`
- load: `cluster image package get -url <redacted-local-or-upload-source:no-package-selected>`
- validate: `cluster image validate -version <target-version>`
- apply: `cluster image update -version <target-version>`

## Blockers
- NetApp cluster management is not configured/reachable yet.
- NetApp API access values are missing; keep values in .env.local.real-lab.
- Current ONTAP version is unknown until ONTAP/API/CLI discovery can run.
- No local ONTAP image package is available from MEDIA_INVENTORY_DIRS or artifacts/Media.
- No target ONTAP version is selected.
- No local ONTAP image/package is selected.
- Pre-upgrade validation has not passed.
- Manual Upgrade Advisor/Health Checker plan is not attached.

## Safety
- Plan only; no ONTAP upgrade command was run.
