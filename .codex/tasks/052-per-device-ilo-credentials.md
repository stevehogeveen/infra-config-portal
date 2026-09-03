# 052 - Per-Device iLO Credentials and Setup Intent

## Goal

Steve added a second iLO device to the rack inventory (`Server 2`) and found
it "stuck" showing the first iLO's (`HPE iLO`, `10.238.207.38`) saved
values. Root cause, confirmed by reading the code: iLO access credentials
and setup intent are **global singletons**, not per-device, even though
`device_inventory` already supports multiple iLO rows:

- `app/backend/app/services/ilo_access_settings.py` reads/writes exactly one
  host/username/password/verify_tls, persisted as `ILO_TEST_HOST` /
  `ILO_TEST_USERNAME` / `ILO_TEST_PASSWORD` / `ILO_TEST_VERIFY_TLS` in
  `.env.local.real-lab` (see `ENV_KEYS`, `_env_path`, `_write_env_updates`).
  There is one env file, so saving credentials for the second iLO overwrites
  the first iLO's credentials.
- `app/backend/app/models.py` `IloSetupIntent` (table `ilo_setup_intents`)
  and `HpeRaidIntent` (table `hpe_raid_intents`) are both keyed only by
  `provider_id` (e.g. `"ilo-redfish"`) — one row total, not one per device.
- Frontend `RackIloConfigurator` / `IloAccessSettingsPanel` /
  `IloSetupIntentWorkspacePanel` (`app/frontend/src/operatorPages.tsx`) and
  `SimpleLabPage`'s `editingIloIsActiveTarget` check
  (`app/frontend/src/simplePages.tsx`) all assume there is exactly one
  "active iLO target" in the whole lab, matched by comparing a device's
  `host` against this single global access-settings host.

Steve's plan is 3 independent physical servers (vCenter/ESXi/vSAN across
them), each with its own iLO. This singleton design is now a hard blocker,
not a cosmetic bug.

## Scope

### Backend

Make iLO credentials, setup intent, and RAID intent per-device:

- Add a `device_id` (FK to `device_inventory.id`) to whatever replaces the
  single credential/intent records. Decide the cleanest of these and pick
  one, consistent with the existing `IloSetupIntent`/`HpeRaidIntent` pattern
  (JSON blob keyed by id) rather than inventing a new storage style:
  - Extend `ilo_setup_intents` and `hpe_raid_intents` primary keys to
    `(device_id, provider_id)` or just `device_id`.
  - Move iLO access credentials (host/username/password/verify_tls) out of
    `.env.local.real-lab` entirely and into a new DB-backed
    `ilo_device_credentials` table keyed by `device_id`, following the same
    SQLAlchemy model conventions as `IloSetupIntent`. Passwords: keep
    whatever at-rest handling the current env-file approach implies (local
    file, not a secrets manager) — do not over-engineer encryption that
    doesn't already exist elsewhere in this codebase, but do not regress
    below the current level of care either.
- Alembic migration: add the new column/table(s), backfill exactly one
  existing device (whichever `device_inventory` row's `host` currently
  matches the legacy `ILO_TEST_HOST`, if any) from the current env values so
  existing local dev/real-lab setups aren't silently wiped.
- API routes (`app/backend/app/api/routes.py`): every iLO access-settings,
  setup-intent, and RAID-intent endpoint needs to accept a `device_id` (path
  or query param) and operate on that device's row only. Keep the
  read-only reachability/inventory probe endpoints working per-device the
  same way (they should already take a target host per call — verify, don't
  assume).
- `read_ilo_access_settings()` / `update_ilo_access_settings()` in
  `ilo_access_settings.py` become device-scoped functions
  (`read_ilo_access_settings(device_id)` /
  `update_ilo_access_settings(device_id, payload)`), backed by the new
  table instead of the env file.

### Frontend

- Every call site that currently calls `api.iloAccessSettings()` /
  `api.iloSetupIntent()` / RAID-intent endpoints without a device id needs
  to pass the selected device's id. Search `app/frontend/src/api.ts` for
  these calls and update signatures + all call sites (`operatorPages.tsx`,
  `simplePages.tsx`).
- `RackIloConfigurator`, `IloAccessSettingsPanel`,
  `IloSetupIntentWorkspacePanel` need the device id threaded through as a
  prop instead of relying on host-string matching against one global
  record.
- `SimpleLabPage`'s `editingIloIsActiveTarget` / "active iLO target" concept
  in `simplePages.tsx` and `RackInspector` in `operatorPages.tsx` can be
  simplified once every iLO device has its own real credentials record —
  "is this the active target" becomes unnecessary; every iLO device just
  reads/writes its own row. Remove the now-dead host-matching logic if it's
  fully superseded, but don't remove anything still load-bearing without
  checking callers first.
- Each iLO's rack tile/inspector/configurator must show and save only its
  own device's data. Two iLOs added and configured independently in the
  same session must never show or write the other's values.

## Explicitly Do NOT

- Do not touch RAID *apply*/reset/rebuild, ESXi install, or any other
  guarded hardware-write path — this task is scoped to credentials/intent
  storage becoming per-device, not new write capability.
- Do not remove the ability to run against a single iLO — this must keep
  working exactly as before for a lab with only one iLO device.
- Do not touch `.env.local.real-lab` content beyond the migration backfill
  read, and do not print/log its contents.
- Do not touch `app/frontend/app/` (pre-existing untracked scratch).
- `PROVIDER_MODE=mock` for all Codex-run tests; no real hardware contact.

## Tests

- Backend: add/adapt tests proving two devices each keep independent
  access-settings, setup-intent, and RAID-intent records — save device A's
  credentials, confirm device B's are unchanged and vice versa. Cover the
  migration backfill (existing single-iLO env values land on the matching
  device, or are dropped cleanly if no device matches).
- e2e: extend or add a Playwright test that adds two iLO devices, saves
  different host/username values on each via the rack-inline configurator,
  reloads, and asserts each device still shows its own saved values (this
  is the literal bug Steve hit).
- Run backend pytest for touched files + ruff; tsc/Playwright if your shell
  allows, otherwise say so and leave them to Claude.

## Docs

Mailbox entry in `app/docs/agent-chat.md`: what was global before, what's
per-device now, the migration/backfill behavior, and any judgment calls on
where the new credentials table lives.

## Leave Uncommitted

Claude reviews, runs full suites, verifies live against the Uplands box
(two real iLOs if available, otherwise mock), and commits.
