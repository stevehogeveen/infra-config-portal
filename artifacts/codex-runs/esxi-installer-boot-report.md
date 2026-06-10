# ESXi Installer Boot Report

## Summary

- checked_at: 2026-06-10T18:46:23.843310+00:00
- status: installed_esxi
- message: Installed ESXi is running and no installer boot override is queued.
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
  "checked_at": "2026-06-10T18:46:23.843310+00:00",
  "installer_detection": {
    "evidence": {
      "boot": {
        "boot_source_override_enabled": "Disabled",
        "boot_source_override_mode": "UEFI",
        "boot_source_override_target": "None",
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
        "AMSDeviceDiscovery": "Complete",
        "DeviceDiscovery": "vMainDeviceDiscoveryComplete",
        "ServerFirmwareInventoryComplete": true,
        "SmartArrayDiscovery": "Complete"
      },
      "hpe_post_state": "FinishedPost",
      "power_state": "On",
      "virtual_media_connected_via": "NotConnected",
      "virtual_media_image_present": false,
      "virtual_media_inserted": false
    },
    "method": "redfish-state",
    "status": "installed_esxi",
    "warnings": []
  },
  "message": "Installed ESXi is running and no installer boot override is queued.",
  "next_safe_action": "Continue with Cisco console and Ethernet bootstrap readiness.",
  "post_system": {
    "boot_source_override_enabled": "Disabled",
    "boot_source_override_mode": "UEFI",
    "boot_source_override_target": "None",
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
  "status": "installed_esxi",
  "virtual_media_after_reset": {
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
  "warnings": []
}
```
