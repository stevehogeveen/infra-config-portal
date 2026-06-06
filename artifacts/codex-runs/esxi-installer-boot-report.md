# ESXi Installer Boot Report

## Summary

- checked_at: 2026-06-06T02:48:58.602889+00:00
- status: boot_requested
- message: ESXi installer or installed ESXi boot state is visible through iLO Redfish.
- report: artifacts/codex-runs/esxi-installer-boot-report.md
- next_safe_action: Continue with Cisco console and Ethernet bootstrap readiness.

## Blockers

- none

## Warnings

- none

## Details

```json
{
  "blockers": [],
  "checked_at": "2026-06-06T02:48:58.602889+00:00",
  "installer_detection": {
    "evidence": {
      "boot": {
        "boot_source_override_enabled": "Once",
        "boot_source_override_mode": "UEFI",
        "boot_source_override_target": "Cd",
        "enabled_allowable_values": [],
        "power_state": "On",
        "status_code": 200,
        "target_allowable_values": [
          "None",
          "Cd",
          "Hdd",
          "Usb",
          "SDCard",
          "Utilities",
          "Diags",
          "BiosSetup",
          "Pxe",
          "UefiShell",
          "UefiHttp",
          "UefiTarget"
        ]
      },
      "boot_progress": null,
      "host_os": {
        "description_hint": "VMware ESXi description present",
        "name": "VMware ESXi",
        "type": 25,
        "version": "8.0.3 Build-24859861 Update 3 Patch 79"
      },
      "hpe_device_discovery": {
        "AMSDeviceDiscovery": "NoAMS",
        "DeviceDiscovery": "Busy",
        "ServerFirmwareInventoryComplete": false,
        "SmartArrayDiscovery": "Complete"
      },
      "hpe_post_state": "InPost",
      "power_state": "On",
      "virtual_media_connected_via": "URI",
      "virtual_media_image_present": true,
      "virtual_media_inserted": true
    },
    "method": "redfish-state",
    "status": "detected",
    "warnings": []
  },
  "message": "ESXi installer or installed ESXi boot state is visible through iLO Redfish.",
  "next_safe_action": "Continue with Cisco console and Ethernet bootstrap readiness.",
  "post_system": {
    "boot_source_override_enabled": "Once",
    "boot_source_override_mode": "UEFI",
    "boot_source_override_target": "Cd",
    "enabled_allowable_values": [],
    "power_state": "On",
    "status_code": 200,
    "target_allowable_values": [
      "None",
      "Cd",
      "Hdd",
      "Usb",
      "SDCard",
      "Utilities",
      "Diags",
      "BiosSetup",
      "Pxe",
      "UefiShell",
      "UefiHttp",
      "UefiTarget"
    ]
  },
  "report": "artifacts/codex-runs/esxi-installer-boot-report.md",
  "status": "boot_requested",
  "virtual_media_after_reset": {
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
  "warnings": []
}
```
