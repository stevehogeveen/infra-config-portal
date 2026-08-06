# 050 - DHCP Addressing Mode (Inventory Devices + iLO Settings)

## Goal

Steve's ask, verbatim: "I am going to need to go DHCP across the board or
allow me to enable it. If I do enable it I would also like to see what
address I end up getting but make sure it's greyed out so the user cannot
touch it."

Two surfaces, one rule: a device can be addressed statically (operator types
the host) or by DHCP (the network assigns it). When DHCP is enabled, the
address field is still shown — populated with the address the device
actually ended up with, when we know it — but disabled/greyed so it cannot
be edited. The address is evidence, not input.

## Scope

### A. Device inventory (shipped in task 048, commit `cbc2a04`)

Backend:
- Add `dhcp_enabled: bool` (default false) to the `DeviceInventory` model,
  `DeviceInventoryWrite`/`Update`/`Read` schemas, and the CRUD flow. No
  migration framework exists; SQLite `create_all` handles new columns only
  for new tables, so add the column the way this repo handles model changes
  elsewhere — check how existing models evolved; if there is no precedent,
  add a small startup-safe `ALTER TABLE ... ADD COLUMN` guard in the service
  or database init, idempotent and crash-safe like the seeder now is.
- When `dhcp_enabled` is true, the stored `host` becomes "last observed
  address" semantics rather than operator intent. PATCHing `host` while
  `dhcp_enabled` is true should be rejected (422) — the UI greys it out, and
  the API should enforce the same rule rather than trust the UI.
- For the seeded `ilo-primary` device the observed address already exists:
  the canonical access-settings host (the sync in `_sync_primary_ilo_host`
  already maintains it). That sync must keep working when `dhcp_enabled` is
  true — for the iLO, DHCP mode makes the sync MORE correct, not less.
- For other device types there is no live address-observation source in this
  app yet. Do not invent one (no ARP/subnet scanning). The stored host, if
  any, displays as the last-known address; if none, the UI shows an explicit
  "No address observed yet" state. Be honest about the limitation.

Frontend (`DeviceInventoryForm`, `GenericDevicePanel`, map):
- The add/edit form gets an addressing choice: Static (default) or DHCP.
  Static → host input editable exactly as today. DHCP → host input disabled
  (visually greyed, `disabled` attribute, not just CSS) showing the observed
  address or the "No address observed yet" placeholder; a short hint under
  it: assigned by the network, not editable.
- The map node meta for a DHCP device shows the observed address with a
  small "DHCP" marker (keep it subtle — a suffix like " · DHCP" is enough).
- The generic detail panel shows the addressing mode and the observed
  address as read-only text when DHCP.

### B. iLO settings drawer (shipped in task 047, commit `336abf2`)

The Network identity section already has the DHCP select (Not set / Off
static / On DHCP) backed by `intent.network.dhcp_enabled`, and the fields
prefill from `discovered-settings`. Change the behavior when the operator
selects "On / DHCP":

- The static address fields — Management IP (state-only today), Subnet Mask
  / Prefix, Gateway — become disabled/greyed. Their displayed values switch
  to the device's discovered current values (the address DHCP actually
  handed out), regardless of any typed desired value, with the existing
  "from device" hint style indicating provenance.
- Saving with DHCP on must NOT persist the discovered echoes as desired
  static values: `cleanIloWorkspaceIntent` (or equivalent) nulls
  `management_ip`, `subnet_mask_or_prefix`, and `gateway` when
  `dhcp_enabled` is true. Desired state is "DHCP", full stop. Flipping back
  to static re-enables the fields with whatever the operator last typed (or
  prefill rules as today).
- DNS Name (hostname) stays editable in both modes — DHCP assigns
  addresses, not the iLO's hostname.
- Do not touch setup-compare/report-preview shapes, and do not add any
  hardware-write path. This is display/persistence logic only.

## Explicitly Do NOT

- No hardware contact, no DHCP server integration, no network scanning, no
  new provider calls. `PROVIDER_MODE=mock` for all Codex-run tests.
- Do not weaken any apply_enabled=false guarantee.
- Do not print/commit secrets; do not touch `.env.local.real-lab`.
- Do not break the seeder's crash-safety (it now recovers from rows-without-
  marker states; keep any schema guard equally idempotent).
- Do not modify `app/frontend/app/` (untracked operator scratch).

## Tests

- Backend: dhcp_enabled round-trips through create/list/patch; PATCH of
  `host` rejected (422) while dhcp_enabled; PATCH flipping dhcp_enabled
  false→true→false preserves the stored host; new-column guard is idempotent
  (call it twice / against an existing table with data).
- Frontend e2e (extend `tests/safe-action-runner.spec.ts`, follow the
  existing mock patterns — inventory mock ids are deliberately UUID-ish, keep
  that): adding a DHCP device shows the greyed host input; the map shows the
  DHCP marker; the iLO drawer with DHCP selected disables the three static
  fields, shows discovered values in them, and the setup-intent PUT body has
  dhcp_enabled=true with null management_ip/subnet/gateway; flipping back to
  static re-enables editing.
- Run backend `pytest tests/test_device_inventory.py tests/test_upgrade_decision.py`
  and `ruff check app tests`, and frontend `npx tsc -b`. Run the focused
  Playwright tests you add if the sandbox allows; if esbuild is still blocked
  (as in task 048), say so plainly in the run report and leave the full
  Playwright run to Claude.

## Docs

Short entry in `app/docs/agent-chat.md`: what changed, the host-PATCH
enforcement rule, and any judgment calls (especially the "No address
observed yet" wording and where the observed address comes from per type).

## Skills

`lab-builder-ux`, `lab-builder-product-craft`, `lab-builder-real-runtime`
(the observed-address-as-evidence rule is exactly its territory).

## Leave Uncommitted

Leave all changes uncommitted. Claude reviews the diff, runs the full
suites, verifies live against the Uplands backend, and commits.
