# Build Verification Classification Report

- Checked at: `2026-06-07T01:16:49.658689+00:00`
- Overall certification state: `blocked_by_prior_stage`
- Provider mode: `local-lab-readwrite`
- Mock results used as substitutes for real lab evidence: `false`

## Classification Vocabulary

- `passed`: check succeeded with current evidence.
- `hard_fail`: configured check failed and is not blocked by an earlier stage.
- `blocked_by_prior_stage`: check must wait for a preceding workflow stage.
- `not_configured_yet`: provider or feature is intentionally not configured for this run.
- `stale_config`: active input or report evidence contains an old lab profile.
- `operator_action_required`: local operator action is required before automation can continue.
- `warning`: informational or indeterminate condition that does not certify readiness.

## Findings

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

### protocol - not_configured_yet

- UI message: NetApp REST is not_configured_yet.
- Report detail: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- Next action: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.

### protocol - not_configured_yet

- UI message: NetApp SSH is not_configured_yet.
- Report detail: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- Next action: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
