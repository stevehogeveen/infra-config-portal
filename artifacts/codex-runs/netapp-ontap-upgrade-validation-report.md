# NetApp ONTAP Upgrade Validation Report

- Checked at: `2026-06-10T00:37:06.217111+00:00`
- Status: `blocked`
- Validation passed: `False`

## Checks
- cluster_management: `blocked`
- access: `blocked`
- current_version: `blocked`
- target_package: `blocked`
- supported_path: `blocked`
- setup_intent: `blocked`

## Blockers
- NetApp cluster management is not configured/reachable yet.
- NetApp API access values are missing; keep values in .env.local.real-lab.
- Current ONTAP version is unknown until ONTAP/API/CLI discovery can run.
- No local ONTAP image package is available from MEDIA_INVENTORY_DIRS or artifacts/Media.
- NetApp setup intent is incomplete.
- No target ONTAP version is selected.
- No ONTAP image/package is selected.
- Supported ONTAP upgrade path is not confirmed.

## Safety
- Validation only; no upgrade apply command was run.
