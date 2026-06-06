# Network Foundation Build Verification Report

- Checked at: `2026-06-06T16:52:43.114790+00:00`
- Command: `PROVIDER_MODE=local-lab-readwrite make provider-lab-build-verification`
- Exit code: nonzero, expected for blocked certification state.
- Build Verification report: `artifacts/codex-runs/build-verification-report.md`
- Redacted summary: `artifacts/codex-runs/build-verification-summary-redacted.json`

## Result

- Status: `blocked`
- Certification state: `blocked_by_prior_stage`
- Mock results used: `False`
- Lab profile: ready for `192.168.1.0/24`.

## Staged Blockers

- Cisco SSH/SCP: `blocked_by_prior_stage`; complete or confirm Cisco console bootstrap, then set `CISCO_MGMT_CONFIGURED=true` before treating SSH/SCP as a port failure.
- ESXi API: `blocked_by_prior_stage`; install/configure ESXi management at `192.168.1.203`, then set `ESXI_CONFIGURED=true` before API certification.
- ESXi SSH: `blocked_by_prior_stage`; install/configure ESXi management and enable/confirm SSH before SSH certification.
- NetApp REST: `not_configured_yet`; leave NetApp unconfigured until its stage is explicitly configured.
- NetApp SSH: `not_configured_yet`; leave NetApp unconfigured until its stage is explicitly configured.

## Safety

- Build Verification did not use mock results as substitutes for real lab results.
- Credential values, tokens, and secrets remain redacted.
