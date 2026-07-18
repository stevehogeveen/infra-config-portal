# Backend Read-Only Button Sweep - 2026-07-18

Scope:
- Safety/button coverage for the current 10-hour Lab Builder simplification goal.
- Mock provider mode only.
- No hardware contact, login, read/write probe, firmware action, RAID action, reset, factory reset, rebuild, or confirmation-gate change.

Commands:

```powershell
$env:PROVIDER_MODE='mock'; .\.venv\Scripts\python.exe -m pytest -q `
  tests/test_netapp_setup_upgrade_center.py::test_iscsi_mock_mode_makes_zero_ssh_or_ontap_contact `
  tests/test_netapp_setup_upgrade_center.py::test_configured_iscsi_iqns_require_no_hardware_contact `
  tests/test_netapp_setup_upgrade_center.py::test_iscsi_partial_write_failure_preserves_evidence `
  tests/test_netapp_setup_upgrade_center.py::test_iscsi_markdown_matches_json_write_evidence `
  tests/test_workflow_action_runner.py::test_netapp_iscsi_apply_uses_request_local_confirmation_context `
  tests/test_workflow_action_runner.py::test_concurrent_workflow_requests_do_not_share_confirmations `
  tests/test_workflow_action_runner.py::test_destructive_action_is_refused `
  tests/test_workflow_action_runner.py::test_write_action_is_refused `
  tests/test_workflow_registry.py::test_safe_read_only_registry_actions_are_ui_runnable `
  tests/test_workflow_registry.py::test_write_destructive_and_unallowlisted_actions_are_not_ui_runnable `
  tests/test_api.py::test_control_action_catalog_exposes_device_actions_without_direct_runs `
  tests/test_api.py::test_control_action_catalog_keeps_netapp_readonly_actions_runnable_when_state_blocked `
  tests/test_api.py::test_control_action_plan_and_run_are_safe_placeholders
```

Result:
- 13 passed in 32.59s.

```powershell
$env:PROVIDER_MODE='mock'; .\.venv\Scripts\python.exe -m pytest -q
```

Result:
- 1097 passed, 3 skipped in 455.05s.

```powershell
npm run test:e2e -- --grep "operator button matrix|overview device workspace matrix|overview faceplate element clicks reveal concise details|safe read-only page action"
```

Result:
- 4 passed.

Notes:
- The targeted backend sweep covered mock-mode zero contact, configured IQNs without hardware contact, partial iSCSI write evidence preservation, JSON/markdown write-evidence parity, request-local confirmation isolation, destructive/write action refusal, read-only action catalog availability, and safe placeholder behavior.
- The frontend button sweep covered the simplified Overview device setup drawer, faceplate element clicks, operator button matrix, and read-only action runner invocation.
