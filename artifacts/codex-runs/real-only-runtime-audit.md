# Real-Only Runtime Audit

Checked at: 2026-06-09

## Scope

This audit covers `/home/administrator/infra-config-portal` source and active
redacted reports. Unit-test fixtures and explicit test-only mock adapters are
kept in scope for automated tests, but they must not appear as operator runtime
state in the running app.

## Test-Only Mock

- `app/backend/app/providers/mock.py` contains the mock source-of-truth and
  mock vSphere adapters used by the VM lifecycle tests.
- `app/backend/tests/*` intentionally assert mock VM lifecycle behavior,
  mock-only artifacts, blocked mock-mode probes, and test fixture redaction.
- `make test`, `make lint`, `app/Makefile backend-test`, and frontend build
  commands explicitly set `PROVIDER_MODE=mock` for automated validation.
- `scripts/codex-common.sh` and Codex wrapper checks keep mock mode for Codex
  test execution; this is test/automation only.

## Runtime Mock

- `runit` loads `.local/app-mode.env` when present but otherwise starts the app
  with `PROVIDER_MODE=mock`.
- Root and app Makefiles define `PROVIDER_MODE ?= mock`, so ad hoc provider
  smoke targets can inherit mock unless a lab target overrides it.
- `app/backend/app/services/provider_mode_settings.py` exposes `mock` as
  "Simulation" and offers a restart command for operator selection.
- `app/backend/app/providers/registry.py` includes mock vSphere,
  mock source-of-truth, mock AWX/OpenTofu/network switch placeholder statuses in
  provider status. In real runtime, these create provider ambiguity.

## Operator UI Mock Labels

- Dashboard and Run Center copy mention "mock workflow queue", "mock-first run
  surface", "mock execution", and "VM Mock Lifecycle".
- Build Verification and Full Rebuild diagnostics show raw "Provider Mode" and
  "Mock Results" fields.
- NetApp observation UI says "Local/mock-only status capture" and "Mock only".
- Reports / Artifacts empty states and artifact cards show "mock-only" and
  "Mock Only" labels.
- VM workflow details show "Mock-Only Safety", "Mock Task", and "Mock VM".
  Those are valid test fixture details, but they must be visually separated
  from real-lab runtime surfaces.

## Stale Artifact Blockers

- `artifacts/codex-runs/netapp-console-discovery-report.md` and its redacted
  JSON contain an old "No OS-visible NetApp USB serial adapters" blocker.
- Newer NetApp live evidence exists:
  `netapp-console-autodiscovery-redacted.json` found the Microchip MCP2221
  adapter at 115200 with `login_required`.
- Newer Cisco evidence exists:
  `cisco-4h-lab-run-details-redacted.json` shows privileged exec, VLAN10 plan
  evidence, reachable management SSH/SCP, and no top-level blockers.
- `build-verification-summary-redacted.json` currently reports
  `provider_mode=mock` while also recording real-lab findings. That must not be
  allowed to certify real results.

## Reports Read As Current State

- `app/backend/app/services/build_verification.py` reads previous local reports
  through `_stale_artifact_evidence()` and puts stale artifacts in the lab
  profile payload.
- `app/backend/app/services/report_center.py` reads static artifact paths for
  Cisco, NetApp, firmware, ESXi, lab profile, and build verification. Without a
  source/freshness model, old artifact blockers can become current issue rows.
- Build Verification currently groups stale lab-profile artifact evidence near
  active profile checks, so historical reports can look like current blockers.

## Make Targets Defaulting To Mock

- Expected test-only mock targets:
  `make test`, `make lint`, `make backend-smoke`, `app backend-test`,
  frontend build, and the explicit VM lifecycle smoke tests.
- Runtime/default ambiguity:
  root `PROVIDER_MODE ?= mock`, app `PROVIDER_MODE ?= mock`, `runit` fallback
  `PROVIDER_MODE=${PROVIDER_MODE:-mock}`, and provider mode settings exposing
  "Simulation" as a selectable operator mode.
- Existing real-lab targets already set `PROVIDER_MODE=local-lab-readwrite`:
  iLO reachability/readiness, firmware compliance, HPE RAID, ESXi boot checks,
  Cisco console workflows, NetApp console/live-state workflows, full rebuild,
  and build verification.

## Build Verification Historical Blocking

- Build Verification can preserve old Cisco/NetApp blockers by reading artifact
  summaries and protocol checks without distinguishing live cached results from
  historical evidence.
- The old NetApp no-adapter report should be Evidence only because newer live
  autodiscovery found the MCP2221 adapter.
- The old Cisco management/bootstrap blocker should be Evidence only when the
  newer live Cisco run reports privileged exec and management readiness.

## Required Cleanup Direction

- Add a shared source model with `source_type`, `checked_at`, `freshness`,
  `stale_after_seconds`, `is_current`, `is_operator_visible`,
  `recheck_command`, and `evidence_artifacts`.
- Treat `live_probe` and fresh `live_cached` as current blocker sources.
- Treat `historical_artifact` as evidence only.
- Treat `test_fixture` as non-operator-visible in real runtime and block real
  certification claims.
- Treat `not_checked` as "Run live check", not as failure.
