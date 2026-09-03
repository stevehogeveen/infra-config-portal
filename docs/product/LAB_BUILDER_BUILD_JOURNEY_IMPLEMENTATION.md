# Lab Builder Build Journey Implementation

Status: implemented and reliability hardened
Branch: `unified-build-journey`
Depends on: Operator Home simplicity slice

## Delivered

- One kit-level workflow engine owns dependency ordering, step lifecycle, pause/resume,
  retry invalidation, persisted run state, and completion reports.
- Persisted runs carry an incrementing revision, selected-kit fingerprint, waiting nonce,
  and execution lease so stale or concurrent mutations fail closed.
- Provider action results are normalized into status, summary, operator message,
  technical details, suggested action, and retry eligibility.
- Fixed kit plans adapt to local RAID, shared storage, NFS or iSCSI, and central
  management features from the active profile.
- Operator Home leads to one Build Plan. The journey then replaces Operator Home in
  place with Build Plan, Run Console, or Completion Report.
- Operator mode shows one status line, one progress result, and one primary action.
  Dependency details and technical evidence remain in one collapsed Advanced log.
- The completion report owns completed, warning, and failure counts and can export a
  Markdown handoff summary.

## Safety Boundary

Read-only and report-only steps may advance automatically. Existing write,
destructive, rebuild, reset, RAID, and upgrade actions are never invoked by the engine
without their existing guarded workflow. The run enters `Waiting`, points the operator
to Details, and continues only when the operator submits the exact action run created
after that wait began. The trace must match the selected kit and its saved profile, and
one guarded trace cannot satisfy two builds. Failed guarded results remain failed.

Retrying a safe step resets every downstream capability to not ready before execution
continues immediately. A failed run cannot use the resume endpoint as an implicit retry,
and a dependency-blocked child cannot retry its owning step. Required skipped steps block
the run; only explicitly optional steps count as complete when skipped.

Safe actions use a 30-minute persisted execution lease. A run recovered after that lease
expires becomes a retryable interrupted failure. Active runs saved before the hardened
revision/profile/evidence contract are stopped and must be restarted from a new plan.

## API

- `GET /api/v1/lab-build/plan`
- `POST /api/v1/lab-build/runs`
- `GET /api/v1/lab-build/runs/latest?kit_id={kit_id}`
- `GET /api/v1/lab-build/runs/{run_id}`
- `POST /api/v1/lab-build/runs/{run_id}/resume`
  - automatic retry body: `{ "run_revision": 12 }`
  - guarded body: `{ "run_revision": 12, "action_run_id": "...", "waiting_nonce": "..." }`
- `POST /api/v1/lab-build/runs/{run_id}/steps/{step_id}/retry`

## Verification

- Backend engine acceptance tests cover ordering, the complete lifecycle, named
  blockers, suggested actions, retry eligibility, downstream invalidation,
  pause/resume, kit-bound evidence, evidence reuse rejection, concurrent resume,
  stale revision and lease recovery, required versus optional skips, legacy recovery,
  and result redaction.
- Browser tests cover one primary action, first-viewport action visibility, mobile
  overflow, kit-scoped recovery, exact guarded continuation payloads, refresh-only
  running states, one completion report, retry visibility, and hidden diagnostics.
- The existing device workspace, firmware, validation, and safety-gate browser suite
  remains the regression gate for this slice.

The hardened branch passed the cumulative Windows fast-verification gate with frontend
build and component checks, 51 Playwright journeys, 85 backend API tests, 10 workflow
diagnosis tests, a valid OpenAPI contract with 142 paths and 158 operations, and all 10
declared QA capabilities satisfied.

## Fresh Launch

Windows operators can start the backend and frontend with
`app/scripts/start-lab-builder.ps1`. The launcher waits for backend health and Operator
Home, honors the explicit/environment/saved operational-mode precedence, records owned
processes, and has a matching verified-process stop command. A separate safe-mock Compose
lane preserves the repository path contract and persistent local/evidence mounts; Linux
CI performs the authoritative fresh-container health and Operator Home smoke.

## Known Boundary

The iSCSI plan uses the existing host-side validation action because the repository does
not yet expose a guarded ESXi iSCSI datastore apply action. The engine reports the real
validation result and does not claim that an unavailable apply capability ran.
