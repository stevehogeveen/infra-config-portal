# Build Verification Classification Report

- Checked at: `2026-06-10T15:39:22.887875+00:00`
- Overall certification state: `test_fixture`
- Source: `test_fixture`
- Freshness: `unknown`
- Current: `False`

## Classification Vocabulary

- `passed`: check succeeded with current evidence.
- `hard_fail`: configured check failed and is not blocked by an earlier stage.
- `blocked_by_prior_stage`: check must wait for a preceding workflow stage.
- `not_configured_yet`: provider or feature is intentionally not configured for this run.
- `stale_config`: active input or report evidence contains an old lab profile.
- `operator_action_required`: local operator action is required before automation can continue.
- `warning`: informational or indeterminate condition that does not certify readiness.

## Findings

### runtime-mode - operator_action_required

- UI message: Build Verification is running in test/mock mode.
- Report detail: Test fixtures cannot produce real lab certification.
- Next action: Run `make provider-lab-build-verification-live` with PROVIDER_MODE=local-lab-readwrite.

### protocol - hard_fail

- UI message: NetApp REST is hard_fail.
- Report detail: NetApp cluster management REST is not reachable.; NetApp API access values are missing; keep any values local and redacted.
- Next action: NetApp cluster management REST is not reachable.

### protocol - hard_fail

- UI message: NetApp SSH is hard_fail.
- Report detail: NetApp cluster management REST is not reachable.; NetApp API access values are missing; keep any values local and redacted.
- Next action: NetApp cluster management REST is not reachable.

### lab-ip-profile - stale_config

- UI message: Active lab IP profile contains stale or mismatched target values.
- Report detail: 2 stale active values; 1 active profile mismatches.
- Next action: Update provider environment inputs to match `Runtime environment` or remove out-of-scope overrides before certification.

### protocol - operator_action_required

- UI message: ESXi ISO media inventory is operator_action_required.
- Report detail: ESXi ISO media inventory is not configured.
- Next action: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.

### protocol - warning

- UI message: iLO Redfish is warning.
- Report detail: Review iLO Redfish readiness.
- Next action: Review iLO Redfish readiness.

### protocol - warning

- UI message: iLO XML fallback is warning.
- Report detail: Review iLO XML fallback readiness.
- Next action: Review iLO XML fallback readiness.

### protocol - warning

- UI message: Cisco SSH/SCP is warning.
- Report detail: Review Cisco SSH/SCP readiness.
- Next action: Review Cisco SSH/SCP readiness.

### protocol - warning

- UI message: ESXi API is warning.
- Report detail: Review ESXi API readiness.
- Next action: Review ESXi API readiness.

### protocol - warning

- UI message: ESXi SSH is warning.
- Report detail: Review ESXi SSH readiness.
- Next action: Review ESXi SSH readiness.
