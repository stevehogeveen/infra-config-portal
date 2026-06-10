# Build Verification Classification Report

- Checked at: `2026-06-10T21:52:14.333870+00:00`
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

### protocol - blocked_by_prior_stage

- UI message: Cisco SSH/SCP is blocked_by_prior_stage.
- Report detail: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.
- Next action: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.

### protocol - blocked_by_prior_stage

- UI message: ESXi API is blocked_by_prior_stage.
- Report detail: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- Next action: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.

### protocol - blocked_by_prior_stage

- UI message: ESXi SSH is blocked_by_prior_stage.
- Report detail: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.
- Next action: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.

### credential - not_configured_yet

- UI message: ilo credential compatibility needs attention.
- Report detail: Field `ILO_TEST_PASSWORD` failed compatibility/configuration; value remains redacted.
- Next action: Set ILO_TEST_PASSWORD in .env.local.real-lab when this provider stage is ready.

### credential - not_configured_yet

- UI message: cisco credential compatibility needs attention.
- Report detail: Field `CISCO_TEST_PASSWORD` failed compatibility/configuration; value remains redacted.
- Next action: Set CISCO_TEST_PASSWORD in .env.local.real-lab when this provider stage is ready.

### credential - not_configured_yet

- UI message: cisco_enable credential compatibility needs attention.
- Report detail: Field `CISCO_ENABLE_PASSWORD or ANSIBLE_CISCO_ENABLE_PASSWORD` failed compatibility/configuration; value remains redacted.
- Next action: Set CISCO_ENABLE_PASSWORD or ANSIBLE_CISCO_ENABLE_PASSWORD in .env.local.real-lab when this provider stage is ready.

### credential - not_configured_yet

- UI message: esxi credential compatibility needs attention.
- Report detail: Field `ESXI_TEST_PASSWORD` failed compatibility/configuration; value remains redacted.
- Next action: Set ESXI_TEST_PASSWORD in .env.local.real-lab when this provider stage is ready.

### protocol - warning

- UI message: iLO Redfish is warning.
- Report detail: Review iLO Redfish readiness.
- Next action: Review iLO Redfish readiness.

### protocol - warning

- UI message: iLO XML fallback is warning.
- Report detail: Review iLO XML fallback readiness.
- Next action: Review iLO XML fallback readiness.
