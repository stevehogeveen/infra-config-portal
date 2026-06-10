# Build Verification Current State Report

- Checked at: `2026-06-10T15:39:22.887875+00:00`
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

## Current Warnings

- Not checked: Review iLO Redfish readiness.
- Not checked: Review iLO XML fallback readiness.
- Not checked: Review Cisco SSH/SCP readiness.
- Not checked: Review ESXi API readiness.
- Not checked: Review ESXi SSH readiness.

## Current Protocol Checks

- `warning` `iLO Redfish` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `iLO XML fallback` source=`not_checked` freshness=`unknown` current=`False`
- `passed` `Cisco console` source=`live_cached` freshness=`stale` current=`False`
- `warning` `Cisco SSH/SCP` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `ESXi API` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `ESXi SSH` source=`not_checked` freshness=`unknown` current=`False`
- `operator_action_required` `ESXi ISO media inventory` source=`not_checked` freshness=`unknown` current=`False`
- `hard_fail` `NetApp REST` source=`live_cached` freshness=`current` current=`True`
- `hard_fail` `NetApp SSH` source=`live_cached` freshness=`current` current=`True`
- `passed` `NetApp console` source=`live_cached` freshness=`current` current=`True`
- `not_in_scope` `NetApp NFS/vCenter` source=`not_checked` freshness=`unknown` current=`False`

## Safety

- No secrets or raw transcripts are included.
