# ESXi One-Time Boot Report

## Summary

- checked_at: 2026-06-05T19:35:48.283126+00:00
- status: set
- message: One-time boot target set to Cd.
- report: artifacts/codex-runs/esxi-one-time-boot-report.md
- next_safe_action: Run controlled server reset to boot the ESXi installer.

## Blockers

- none

## Warnings

- none

## Details

```json
{
  "after": {
    "boot_source_override_enabled": "Once",
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
  "before": {
    "boot_source_override_enabled": "Once",
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
  "blockers": [],
  "checked_at": "2026-06-05T19:35:48.283126+00:00",
  "message": "One-time boot target set to Cd.",
  "next_safe_action": "Run controlled server reset to boot the ESXi installer.",
  "patch": {
    "method": "PATCH",
    "path": "/redfish/v1/systems/1/",
    "request": {
      "Boot": {
        "BootSourceOverrideEnabled": "Once",
        "BootSourceOverrideTarget": "Cd"
      }
    },
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
  "report": "artifacts/codex-runs/esxi-one-time-boot-report.md",
  "status": "set",
  "target": "Cd",
  "warnings": []
}
```
