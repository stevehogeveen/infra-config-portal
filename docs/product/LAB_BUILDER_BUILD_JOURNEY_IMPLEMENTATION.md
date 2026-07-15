# Lab Builder Build Journey Implementation

Status: implemented vertical slice
Branch: `unified-build-journey`
Depends on: Operator Home simplicity slice

## Delivered

- One kit-level workflow engine owns dependency ordering, step lifecycle, pause/resume,
  retry invalidation, persisted run state, and completion reports.
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
to Details, and resumes only after a new successful action trace proves that guarded
step completed.

Retrying a safe step resets every downstream capability to not ready before execution
can continue. A failed run cannot use the resume endpoint as an implicit retry.

## API

- `GET /api/v1/lab-build/plan`
- `POST /api/v1/lab-build/runs`
- `GET /api/v1/lab-build/runs/latest`
- `GET /api/v1/lab-build/runs/{run_id}`
- `POST /api/v1/lab-build/runs/{run_id}/resume`
- `POST /api/v1/lab-build/runs/{run_id}/steps/{step_id}/retry`

## Verification

- Backend engine acceptance tests cover ordering, the complete lifecycle, named
  blockers, suggested actions, retry eligibility, downstream invalidation,
  pause/resume, explicit retry boundaries, and redacted exceptions.
- Browser tests cover one primary action, first-viewport action visibility, mobile
  overflow, guarded waiting, one completion report, retry visibility, and hidden
  technical diagnostics.
- The existing device workspace, firmware, validation, and safety-gate browser suite
  remains the regression gate for this slice.

## Known Boundary

The iSCSI plan uses the existing host-side validation action because the repository does
not yet expose a guarded ESXi iSCSI datastore apply action. The engine reports the real
validation result and does not claim that an unavailable apply capability ran.
