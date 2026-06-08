# ESXi Virtual Media Eject Report

## Summary

- checked_at: 2026-06-07T13:30:46.772913+00:00
- status: ejected
- message: ESXi ISO virtual media is ejected.
- report: artifacts/codex-runs/esxi-virtual-media-eject-report.md
- next_safe_action: Confirm ESXi is running from installed boot media and rerun ESXi readiness.

## Blockers

- none

## Warnings

- none

## Details

```json
{
  "after": {
    "actions": [
      "#VirtualMedia.EjectMedia",
      "#VirtualMedia.InsertMedia"
    ],
    "connected_via": "NotConnected",
    "id": "2",
    "image_present": false,
    "inserted": false,
    "media_types": [
      "CD",
      "DVD"
    ],
    "name": "VirtualMedia",
    "status_code": 200
  },
  "before": {
    "actions": [
      "#VirtualMedia.EjectMedia",
      "#VirtualMedia.InsertMedia"
    ],
    "connected_via": "URI",
    "id": "2",
    "image_present": true,
    "inserted": true,
    "media_types": [
      "CD",
      "DVD"
    ],
    "name": "VirtualMedia",
    "status_code": 200
  },
  "blockers": [],
  "checked_at": "2026-06-07T13:30:46.772913+00:00",
  "device": {
    "path": "/redfish/v1/Managers/1/VirtualMedia/2/"
  },
  "eject_request": {
    "method": "POST",
    "path": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.EjectMedia/",
    "request": {},
    "response": {
      "error": {
        "@Message.ExtendedInfo": [
          {
            "MessageId": "Base.1.18.Success"
          }
        ],
        "code": "iLO.0.10.ExtendedInfo",
        "message": "See @Message.ExtendedInfo for more information."
      }
    },
    "status_code": 200
  },
  "ejected": true,
  "message": "ESXi ISO virtual media is ejected.",
  "next_safe_action": "Confirm ESXi is running from installed boot media and rerun ESXi readiness.",
  "report": "artifacts/codex-runs/esxi-virtual-media-eject-report.md",
  "status": "ejected",
  "warnings": []
}
```
