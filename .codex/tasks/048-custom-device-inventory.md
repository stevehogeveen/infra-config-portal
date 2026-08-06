# 048 - Custom Device Inventory (Add Arbitrary Devices Beyond The Fixed 4 Slots)

## Goal

Steve's product direction, verbatim: "We will also need the ability to add
more machines, whether that be switches, servers, netapps, esxi, vcenters,
ect. lets go completely custom now."

Today the topology is a fixed set of role slots — the map/device model
assumes exactly one Cisco switch, one iLO/server, one ESXi host, one NetApp,
rendered from a hardcoded lab-profile shape (see the "position:
cisco|server|netapp|datastore|vcenter" role-slot history in
`app/docs/agent-chat.md`'s 2026-07-07 entry — this was already flagged as not
scaling). Replace the fixed-slot model with an operator-managed device
inventory: add, edit, and remove devices of arbitrary type and arbitrary
count, and have the topology map render whatever the operator has actually
added.

## Scope

### Data model

Add a persisted device inventory (new table/model, following the existing
pattern used for `IloSetupIntent` etc. in `app/backend/app/models.py`):

- `id` (stable identifier)
- `device_type` (an open set: at minimum `ilo`, `cisco_switch`, `esxi_host`,
  `netapp`, `vcenter`, `other` — but the picker should not hard-block a type
  Steve didn't think to enumerate; use a free-text label alongside the type
  enum, not just the enum, so "other" devices are still meaningfully named)
- `display_name`
- `host` (IP/hostname, optional — a device can exist before it has an
  address)
- `notes` (optional free text)
- created/updated timestamps

This is a general inventory record, not a replacement for the existing
provider-specific config (`IloSetupIntent`, `IloAccessSettingsWrite`, ESXi/
NetApp/Cisco env-var config, etc.) — those stay as they are. A device
inventory entry of type `ilo` should link to / stay consistent with the
existing iLO access-settings host rather than creating a second, divergent
source of truth for the iLO host address. Use your judgment on the cleanest
way to reconcile "one canonical iLO host" with "operator can rename/re-tag it
in the inventory" — document the decision in the run report.

### Backend API

CRUD endpoints for the device inventory, e.g. under
`/api/v1/device-inventory`: list, create, update, delete. Follow this
codebase's existing conventions (Pydantic schemas in `app/schemas.py`,
service functions in `app/services/`, routes in `app/api/routes.py`).

### Frontend

- An "Add device" affordance on the topology/overview page (reuse the
  existing "Create or change kit" entry point pattern in
  `app/frontend/src/App.tsx`/`operatorPages.tsx` if there's a natural fit, or
  add a clearly-labeled new one) that opens a small form: type, name, host,
  notes.
- The topology map must render however many devices actually exist —
  including more than one of the same type (e.g. two Cisco switches, three
  ESXi hosts) — not just the historical fixed 4 slots. Reuse the existing
  zone/auto-layout work from the 2026-07 ZONES redesign (see mailbox
  2026-07-07 entry) rather than reintroducing hardcoded position slots.
- Clicking a device of a type this app already understands (`ilo`,
  `cisco_switch`, `esxi_host`, `netapp`) should open the existing
  type-specific drawer (iLO drawer, Cisco console drawer, etc.) — do not
  duplicate that logic; the inventory entry should just be another way to
  reach the same drawers, keyed by device id/host instead of a hardcoded
  slot.
- Clicking a device of an unrecognized/`other` type, or a `vcenter` device
  (no dedicated drawer exists yet per earlier mailbox notes — vCenter is
  `VCENTER_CONFIGURED`/env-var only today, no UI), should open a generic
  read-only detail panel (name, type, host, notes, delete button) rather than
  erroring or silently doing nothing.
- Removing a device from the inventory must not delete any real underlying
  provider configuration (e.g. removing an `ilo`-typed inventory entry should
  not clear `ILO_TEST_HOST` or saved iLO credentials) — it only removes it
  from the visual/inventory list. Note this constraint clearly to the
  operator in the delete confirmation if you add one.

## Explicitly Do NOT

- Do not make this device inventory a live hardware-write surface. Adding a
  device to the inventory never contacts hardware, probes anything, or writes
  provider config by itself — it is purely "operator says this device
  exists," same trust level as typing a name into a form.
- Do not remove or break the existing 4 device drawers (iLO, Cisco, ESXi,
  NetApp) — they must keep working exactly as today when reached through the
  new inventory-driven map.
- Do not silently drop devices that exist today (the current
  lab-profile-derived Cisco/iLO/ESXi/NetApp nodes) when this ships — migrate/
  seed them into the new inventory model so nothing appears to vanish for an
  operator who already has a working lab profile.
- Do not make real vSphere, ESXi, iLO, NetApp, or switch provider calls from
  this feature or its tests. `PROVIDER_MODE=mock` for all Codex-run tests.
- Do not print/commit secrets.
- Do not touch `.env.local.real-lab` or any credential file.

## Tests

- Backend: CRUD round-trip tests for the device inventory endpoints
  (create/list/update/delete, validation of required fields, that deleting an
  inventory entry doesn't touch provider env/credential config).
- Frontend: adding a device via the UI causes a new node to render on the
  map; removing one removes it; clicking a known-type device opens the
  correct existing drawer; clicking an unknown-type device opens the generic
  panel; the pre-existing 4 devices are still present after the migration/
  seed.
- Run backend `pytest` and `ruff check`, frontend `npm run build` and
  `npm run test:e2e` (or the relevant focused subset) before finishing. Do not
  claim a suite is green without having just run it.

## Docs

Leave a short entry in `app/docs/agent-chat.md` describing the new data
model, the migration/seed approach for existing devices, and any product
judgment calls (especially the "one canonical iLO host vs. operator-renamed
inventory entry" reconciliation).

## Skills

Use `lab-builder-ux` and `lab-builder-product-craft` for the map/inventory UI
work; use `lab-builder-dual-app-architecture` if you need to check how
`lab-builder` (the reference app) already models multi-device inventories,
since this may already be a solved problem there. List which skills you
applied in the run report.

## Leave Uncommitted

Leave all changes uncommitted in the working tree. Steve/Claude will review
the diff and commit.

## Sequencing

This task should run AFTER `.codex/tasks/047-editable-current-state-settings.md`
has been completed and reviewed (run one Codex task at a time in this repo;
do not start this while 047 is still in flight, to avoid working-tree
contention).
