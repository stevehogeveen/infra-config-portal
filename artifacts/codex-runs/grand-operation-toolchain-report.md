# Grand Operation Stage 2 Toolchain Readiness Report

Generated: 2026-06-10T18:17:35-04:00

## Summary

Stage 2 status: warning.

No required tool is missing. The only missing requested tool family is optional `pyATS/Genie`; it was not installed because it is large and not required for the current console-first Cisco workflow.

## Installed During This Run

Installed into ignored local paths only:

- Backend virtualenv `app/backend/.venv`:
  - `ansible-core`
  - `netmiko`
  - `netapp-ontap`
  - `ilorest`
- Repo-local Ansible collection path `.local/ansible/collections`:
  - `cisco.ios`
  - dependency `ansible.netcommon`
  - dependency `ansible.utils`
- Repo-local binary path `.local/bin`:
  - `govc`

No credentials were used or printed during tool installation.

## Current Tool Availability

| Tool | Status | Version / Detail | Location |
| --- | --- | --- | --- |
| `pyserial` | ready | `3.5` | backend virtualenv |
| `ansible` | ready | `ansible [core 2.21.0]` | `app/backend/.venv/bin/ansible` |
| `cisco.ios` collection | ready | `11.4.1` | `.local/ansible/collections` |
| `netmiko` | ready | `4.7.0` | backend virtualenv |
| `govc` | ready | `0.54.1` | `.local/bin/govc` |
| `netapp-ontap` | ready | `9.18.1.0` | backend virtualenv |
| `ilorest` | ready | `RESTful Interface Tool 7.2.0.0` | `app/backend/.venv/bin/ilorest` |
| `pyATS/Genie` | optional missing | not installed | not applicable |

## App Toolchain Detection Fix

The app originally detected CLIs only through the process `PATH`, which missed tools installed into the backend virtualenv and repo-local `.local/bin`.

Updated `app/backend/app/services/build_verification.py` so Toolchain Readiness checks:

- `app/backend/.venv/bin` from the active Python executable.
- `.local/bin` for repo-local helper binaries.
- `.local/ansible/collections` for repo-local Ansible collections.

Fresh `make provider-lab-toolchain-check` result:

```json
{
  "status": "warning",
  "required_missing": [],
  "optional_missing": [
    "pyATS/Genie"
  ],
  "artifacts": {
    "report": "artifacts/codex-runs/toolchain-availability-report.md"
  }
}
```

## Validation

Targeted validation passed:

```text
ruff check app/services/build_verification.py tests/test_media_inventory.py tests/test_firmware_compliance.py: passed
pytest tests/test_media_inventory.py tests/test_firmware_compliance.py tests/test_build_verification.py: 48 passed
```

## Remaining Toolchain Gap

`pyATS/Genie` remains optional. Install it only if Cisco command parsing or model-based validation becomes necessary during the Cisco stage.

Next action: Stage 3 Cisco switch discovery and validation.
