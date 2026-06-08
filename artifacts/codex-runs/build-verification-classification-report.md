# Build Verification Classification Report

- Checked at: `2026-06-08T14:47:17.555667+00:00`
- Overall certification state: `stale_config`
- Provider mode: `mock`
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

### lab-ip-profile - stale_config

- UI message: Active lab IP profile contains stale or mismatched target values.
- Report detail: 1 stale active values; 0 active profile mismatches.
- Next action: Update provider environment inputs to match `Runtime environment` and remove stale 10.10.8.x values before certification.

### protocol - operator_action_required

- UI message: NetApp console is operator_action_required.
- Report detail: Use the selected candidate as the next physical console check, then verify cable placement, adapter ownership, power state, and baud before rerunning discovery.
- Next action: Use the selected candidate as the next physical console check, then verify cable placement, adapter ownership, power state, and baud before rerunning discovery.

### protocol - operator_action_required

- UI message: ESXi ISO media inventory is operator_action_required.
- Report detail: ESXi ISO media inventory is not configured.
- Next action: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.

### protocol - blocked_by_prior_stage

- UI message: NetApp NFS/vCenter is blocked_by_prior_stage.
- Report detail: Use console/API read-only discovery to identify the NetApp state, then configure vCenter/govc before NFS datastore apply is implemented.
- Next action: Use console/API read-only discovery to identify the NetApp state, then configure vCenter/govc before NFS datastore apply is implemented.

### protocol - not_configured_yet

- UI message: NetApp REST is not_configured_yet.
- Report detail: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.
- Next action: Leave NetApp REST as not_configured_yet until the NetApp stage is explicitly configured.

### protocol - not_configured_yet

- UI message: NetApp SSH is not_configured_yet.
- Report detail: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.
- Next action: Leave NetApp SSH as not_configured_yet until the NetApp stage is explicitly configured.

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
