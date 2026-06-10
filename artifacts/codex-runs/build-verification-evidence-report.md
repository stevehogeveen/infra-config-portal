# Build Verification Evidence Report

- Checked at: `2026-06-10T15:39:22.887875+00:00`
- Historical artifacts are evidence only and do not create current blockers by themselves.

## Evidence Artifacts

- `artifacts/codex-runs/build-verification-report.md`
- `artifacts/codex-runs/build-verification-current-state-report.md`
- `artifacts/codex-runs/build-verification-evidence-report.md`
- `artifacts/codex-runs/build-verification-summary-redacted.json`

## Stale Evidence

- `artifacts/codex-runs/overnight-lab-builder-final-report.md`: Regenerate this report after confirming the 192.168.1.0/24 lab profile.

## Raw Finding Sources

- `operator_action_required` `runtime-mode` source=`test_fixture` freshness=`unknown` current=`False`
- `hard_fail` `protocol` source=`live_cached` freshness=`current` current=`True`
- `hard_fail` `protocol` source=`live_cached` freshness=`current` current=`True`
- `stale_config` `lab-ip-profile` source=`live_cached` freshness=`current` current=`True`
- `operator_action_required` `protocol` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `protocol` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `protocol` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `protocol` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `protocol` source=`not_checked` freshness=`unknown` current=`False`
- `warning` `protocol` source=`not_checked` freshness=`unknown` current=`False`

## Safety

- Credential values, tokens, and secrets are redacted.
