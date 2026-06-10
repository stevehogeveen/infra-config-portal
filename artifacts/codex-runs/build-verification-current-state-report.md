# Build Verification Current State Report

- Checked at: `2026-06-10T21:52:14.333870+00:00`
- Status: `blocked`
- Source: `test_fixture`
- Freshness: `unknown`
- Current: `False`
- Recheck: `make provider-lab-build-verification-live`

## Current Blockers

- Test fixture: Run `make provider-lab-build-verification-live` with PROVIDER_MODE=local-lab-readwrite.
- Last live result: NetApp cluster management REST is not reachable.
- Last live result: NetApp cluster management REST is not reachable.
- Last live result: Update provider environment inputs to match `Runtime environment` or remove out-of-scope overrides before certification.
- Not checked: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.
- Not checked: Complete or confirm Cisco console bootstrap, then set CISCO_MGMT_CONFIGURED=true before treating SSH/SCP as a port failure.
- Not checked: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- Not checked: Install/configure ESXi management and enable/confirm SSH before ESXi SSH certification.

## Current Warnings

- Not checked: Review iLO Redfish readiness.
- Not checked: Review iLO XML fallback readiness.

## Current Protocol Checks

- `warning` `iLO Redfish` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `iLO XML fallback` source=`not_checked` freshness=`unknown` current=`False`
- `passed` `Cisco console` source=`live_cached` freshness=`stale` current=`False`
- `blocked_by_prior_stage` `Cisco SSH/SCP` source=`not_checked` freshness=`unknown` current=`False`
- `blocked_by_prior_stage` `ESXi API` source=`not_checked` freshness=`unknown` current=`False`
- `blocked_by_prior_stage` `ESXi SSH` source=`not_checked` freshness=`unknown` current=`False`
- `operator_action_required` `ESXi ISO media inventory` source=`not_checked` freshness=`unknown` current=`False`
- `hard_fail` `NetApp REST` source=`live_cached` freshness=`current` current=`True`
- `hard_fail` `NetApp SSH` source=`live_cached` freshness=`current` current=`True`
- `passed` `NetApp console` source=`live_cached` freshness=`current` current=`True`
- `not_in_scope` `NetApp NFS/vCenter` source=`not_checked` freshness=`unknown` current=`False`

## Safety

- No secrets or raw transcripts are included.
