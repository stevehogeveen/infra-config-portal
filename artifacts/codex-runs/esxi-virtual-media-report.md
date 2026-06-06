# ESXi Virtual Media Report

## Summary

- checked_at: 2026-06-06T02:48:50.151057+00:00
- status: inserted
- message: ESXi ISO is inserted through iLO VirtualMedia.
- report: artifacts/codex-runs/esxi-virtual-media-report.md
- next_safe_action: Set one-time boot target to virtual CD/DVD.

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
  "checked_at": "2026-06-06T02:48:50.151057+00:00",
  "connected_via": "URI",
  "device": {
    "id": "2",
    "insert_target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.InsertMedia/",
    "media_types": [
      "CD",
      "DVD"
    ],
    "name": "VirtualMedia",
    "path": "/redfish/v1/Managers/1/VirtualMedia/2/"
  },
  "insert_request": {
    "method": "POST",
    "path": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.InsertMedia/",
    "request": {
      "Image": "http://192.168.1.19:8088/VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso",
      "Inserted": true,
      "TransferProtocolType": "HTTP"
    },
    "response": {
      "error": {
        "@Message.ExtendedInfo": [
          {
            "MessageId": "iLO.2.25.MaxVirtualMediaConnectionEstablished"
          }
        ],
        "code": "iLO.0.10.ExtendedInfo",
        "message": "See @Message.ExtendedInfo for more information."
      }
    },
    "status_code": 400
  },
  "inserted": true,
  "media_url": "http://192.168.1.19:8088/VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso",
  "message": "ESXi ISO is inserted through iLO VirtualMedia.",
  "next_safe_action": "Set one-time boot target to virtual CD/DVD.",
  "report": "artifacts/codex-runs/esxi-virtual-media-report.md",
  "selected_iso": {
    "directory": "/home/REDACTED/infra-config-portal/artifacts/Media",
    "name": "VMware-ESXi-8.0.3-24859861-HPE-803.0.0.12.2.0.9-oct2025.iso",
    "selection": "preferred-esxi-8",
    "size_bytes": 767496192
  },
  "status": "inserted",
  "warnings": []
}
```
