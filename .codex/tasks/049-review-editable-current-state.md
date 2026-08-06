# 049 - Read-Only Review: Editable Current-State Settings (047)

## Goal

Review-only task. Claude implemented `.codex/tasks/047-editable-current-state-settings.md`
directly (during the sandbox outage) and the diff is sitting **uncommitted**
in the working tree. Critique it before it gets committed. Do not modify any
file; produce your findings as the run report only.

## What landed (read the actual diff with `git diff` + `git status`)

Backend:
- New `GET /api/v1/providers/ilo-redfish/discovered-settings` endpoint
  (`app/api/routes.py`), schemas `IloDiscovered*` in `app/schemas.py`,
  service `get_ilo_discovered_settings()` in
  `app/services/ilo_readiness.py`. Returns raw current values from the
  cached read-only probe for operator prefill; values stored as the literal
  string `REDACTED` in the probe cache (they matched the configured
  host/username at redaction time) are substituted from
  `IloRedfishConfig.from_settings()` — the operator typed those values in the
  first place. Missing/unsupported values come back null, never fabricated.

Frontend (`operatorPages.tsx`, `api.ts`, `types.ts`, `styles.css`):
- `IloSetupIntentWorkspacePanel` fetches discovered-settings alongside
  setup-intent; each form field prefers saved intent, falls back to the
  discovered value, else blank. A subtle "from device" hint shows while a
  field still equals the device-reported value (computed by comparison, so
  editing hides it and typing the value back restores it).
- `hasSavedIntent` (from created_at/updated_at) gates non-null-default fields
  (snmp.enabled): a server default from an unsaved record must not shadow a
  real device value.
- Local RAID planner: new `localRaidLiveSeed()` derives draft bay
  assignments + RAID levels from discovered logical drives (lowest-numbered
  volume → boot, rest → datastore, dedicated/standby spares → spare,
  unattached → unused; single-volume heuristic: <=2 member drives → boot,
  else datastore). The seed only replaces the draft when the operator's
  existing draft still equals the canned template ("untouched"), so operator
  customizations always win. Meta line gains "draft starts from the live
  layout".
- Heading renames: "iLO setup settings"→"iLO settings" (aria-label
  unchanged), "Local user references"→"Local users", save message reworded.

Tests: 3 new backend tests (test_upgrade_decision.py), 4 new e2e tests
(safe-action-runner.spec.ts), 1 e2e assertion updated for the rename. Full
backend suite: 267 tests, 1 pre-existing failure
(`test_ilo_setup_apply_endpoint_blocked_by_default`, the known 422-vs-200
from the 2026-07-23 mailbox — verified identical with the diff stashed).

## Questions I most want your judgment on

1. Redaction boundary: is substituting REDACTED values server-side from the
   operator's own saved config acceptable, or does it create a path where a
   report/artifact could later embed those values? (The compare/report
   endpoints were deliberately untouched.)
2. The `hasSavedIntent` gate: any edge where an operator's genuine saved
   "snmp disabled" gets overridden, or a stale device read shadows intent?
3. `localRaidLiveSeed` volume→group heuristics: sane? Where do they lie to
   the operator? (Known limitation: on the Uplands DL380, volume member
   resources are Storage-view paths while drives are SmartStorage-view
   paths, so pairing fails and everything seeds "unused" — same limitation
   as the pre-existing "Live:" captions. Cross-view pairing via
   hardware_identity_fingerprint_sha256 looks feasible — assess whether that
   should be the next slice.)
4. The "untouched draft" detection (draft equals canned template → adopt live
   seed): any scenario where an operator's deliberate choice happens to equal
   the canned template and gets silently replaced?
5. Anything in the diff that violates the app's honesty rules (mock vs live,
   false-green, exact-target evidence).

## Explicitly Do NOT

- Do not edit, stage, commit, or revert anything.
- Do not run destructive or hardware-contacting commands. Running the
  existing backend pytest / frontend Playwright suites in mock mode is fine.
- Do not print secrets.

## Skills

`lab-builder-real-runtime` (honesty/evidence rules) and `lab-builder-ux`.
