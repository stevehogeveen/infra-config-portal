# Cisco Network Foundation Baseline

- Checked at: `2026-06-06T16:47:13Z`
- Working tree: dirty before this run; existing lab artifacts and UI output were preserved.
- Provider mode for this run: `local-lab-readwrite`
- Env file presence: `.env.local.real-lab` present; secret values not printed.

## Current Report Baseline

- Cisco console readiness report: `artifacts/codex-runs/cisco-console-ethernet-readiness-report.md`
- Cisco latest real-lab workflow report: `artifacts/codex-runs/cisco-4h-lab-run-report.md`
- Cisco bootstrap apply report: `artifacts/codex-runs/cisco-bootstrap-apply-report.md`
- ESXi install readiness report: `artifacts/codex-runs/esxi-install-readiness-report.md`
- Build Verification report: `artifacts/codex-runs/build-verification-report.md`
- Build Verification classification report: `artifacts/codex-runs/build-verification-classification-report.md`

## Baseline Findings

- Build Verification used the active `192.168.1.0/24` lab profile.
- Cisco management target was `192.168.1.204` in active settings.
- ESXi management target was `192.168.1.203` in active settings.
- NetApp was not configured for this run.
- Earlier Cisco apply evidence contained stale `10.10.8.x` text and needed regeneration.
- No mock results were accepted as substitutes for real-lab evidence.

## Safety

- Credentials, tokens, raw env values, and raw console transcripts were not printed or stored in this baseline.
