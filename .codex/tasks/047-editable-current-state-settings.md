# 047 - Editable Current-State Settings (Replace Desired-vs-Discovered With Direct Edit)

## Goal

Steve's product direction, verbatim: "what i want to see is what is there and I
want to be able to change it. so in other words I don't want to see what it
should be and what it is any more, i just want to see an input of what it is
and allow me to change it or not."

Today the iLO drawer has two disconnected pieces:
1. "Sign in and first contact" — real reachability/identity evidence.
2. "iLO setup settings" — a blank plan-only intent form (network/DNS/NTP/
   license/SNMP/IPv6/users), unrelated to whatever iLO actually reports.

Collapse this into ONE editable settings surface per field: pre-fill each
input with the real discovered value from iLO when it's known, and let the
operator directly edit it. Editing and saving just writes the new desired
value (existing `setup-intent` PUT), same as today — the only change is what
the input shows before the operator touches it, and removing any "desired vs
discovered / match / mismatch" language or UI from the operator-facing drawer.
The same principle applies to the storage/RAID drawer.

## Why This Data Already Exists

`app/backend/app/providers/ilo_redfish.py`'s `probe()` already reads real
values via read-only Redfish GETs and stores them in the cached probe result
under these keys (see `_manager_network_identity`, `_manager_time_and_dns_settings`,
`_manager_license_summaries`, `_account_service_users`):

- `network_identity`: `status`, `dns_name`, `fqdn_value`, `dhcp_enabled`,
  `ip_address`, `subnet_mask`, `gateway`, `vlan_enabled`, `vlan_id`,
  `name_servers` (list)
- `time_and_dns`: `status`, `timezone`, `ntp_servers` (list),
  `ntp_protocol_enabled`, `domain_name`, `dns_servers` (list),
  `snmp_protocol_enabled`
- `licenses`: list of `{name, product_type, status_state}`
- `local_users`: list of `{username, role, enabled}` (no passwords, ever)

`app/backend/app/services/ilo_readiness.py` already has helper functions that
read these from the cache (`_discovered_network_identity`,
`_discovered_time_and_dns`, `_discovered_license_status`,
`_discovered_local_usernames`) — reuse or adapt this pattern, don't
reimplement Redfish reads.

**Important:** those helpers currently feed `setup-compare`, which
deliberately redacts real values behind labels like "matches saved intent"
for report safety. That redaction is correct for `setup-compare` /
`report-preview` (report artifacts that get shared/archived) but wrong for
this feature — the operator is looking at their own drawer, in their own
browser, viewing their own hardware's real config, not a shareable report. Do
not reuse the redacted compare rows for prefill; read the raw discovered
values directly.

## Scope

### Backend

Add a new read-only endpoint that returns the current discovered iLO settings
in the same shape as `IloSetupIntentWrite` (or close enough that the frontend
can map it 1:1 onto the existing setup-settings form fields), sourced from the
cached probe result — e.g.
`GET /api/v1/providers/ilo-redfish/discovered-settings`. Missing/unavailable
values (probe never run, or a given Redfish resource unsupported) should come
back as `null`/absent, not a fabricated value — the frontend must be able to
tell "unknown" apart from "actually empty on the device."

Do NOT touch:
- `setup-compare`, `report-preview` schemas/behavior (leave as-is; they still
  serve their own report/audit purpose)
- Anything that writes to hardware
- The `probe()` Redfish-read logic itself (it's already correct — just expose
  what it already collects)

### Frontend

In `app/frontend/src/operatorPages.tsx` (iLO setup settings section, and the
`api.ts` client), on drawer open:
1. Fetch the new discovered-settings endpoint alongside the existing
   `setup-intent` fetch.
2. For each input, if a saved desired value exists use it; otherwise if a
   discovered value exists, use it as the initial/pre-filled value; otherwise
   leave blank. (Saved operator intent always wins over a stale discovery —
   don't clobber something the operator already typed.)
3. Remove any language framing this as a "plan" that "does not write iLO" if
   it now reads as showing live values — keep the real safety fact (typing
   here still only saves locally; it does not touch hardware) but don't imply
   the field is empty/fictional when it's pre-filled with a real reading.
4. Add a lightweight visual affordance so the operator can tell "this came
   from the device" vs "this is what you typed" (e.g. a small "from device"
   hint under a field until edited) — keep it subtle, not another compare UI.

Apply the same "editable input pre-filled with current value" pattern to the
storage/RAID drawer (`Local storage` node → RAID drive planner). Today it
shows nothing until "iLO Inventory Read" runs, then presumably lists bays.
Once storage inventory is available, the operator should see the actual
current logical drive layout (name, RAID type, member bays, capacity) as
editable fields representing the desired layout going forward, not a
separate "plan vs discovered" comparison. If a real apply/write path doesn't
exist yet for RAID, that's fine and out of scope here — this task is about
what's *shown and editable*, not adding new write capability. Do not add any
new RAID write/apply action in this task.

## Explicitly Do NOT

- Do not add or enable any new hardware-write path (iLO setup apply, RAID
  apply, ESXi, Cisco, NetApp). This is a read + local-save-only UI change.
- Do not remove or weaken the existing `apply_enabled: false` /
  plan-only guarantees anywhere.
- Do not touch `setup-compare` or `report-preview` output shape — other code
  may depend on their current redacted format.
- Do not make real hardware calls from tests. `PROVIDER_MODE=mock` for all
  Codex-run tests, per `.codex/README.md`.
- Do not print/commit secrets, license keys, or passwords.
- Do not touch `.env.local.real-lab` or any credential file.

## Tests

- Backend: new tests for the discovered-settings endpoint covering: no cached
  probe (all fields null/absent), a fully-populated cached probe (all fields
  present and correctly mapped), and a partially-available probe (e.g.
  `network_identity.status != "ok"` → those fields null, other sections still
  populated). Follow the existing test patterns in
  `app/backend/tests/test_upgrade_decision.py` (`record_probe_result`,
  `clear_probe_results`, `TestClient`).
- Frontend: component/e2e coverage that a field pre-fills from a discovered
  value when no saved intent exists, that a saved intent value wins over a
  discovered one, and that editing+saving still calls the existing
  `setup-intent` save path unchanged.
- Run backend `pytest` and `ruff check`, frontend `npm run build` and
  `npm run test:e2e` (or the relevant focused subset) before finishing. Do not
  claim a suite is green without having just run it.

## Docs

- Leave a short entry in `app/docs/agent-chat.md` (the shared Claude/Codex
  mailbox) describing what changed, the new endpoint path, and any UI/product
  judgment calls you made (e.g. exactly how "from device" is indicated).

## Skills

Use `lab-builder-ux` and `lab-builder-product-craft` for this task — this is
squarely their domain (setup page layout, action-first controls, mock-state
clarity). List which skills you applied in the run report.

## Leave Uncommitted

Leave all changes uncommitted in the working tree. Steve/Claude will review
the diff and commit.
