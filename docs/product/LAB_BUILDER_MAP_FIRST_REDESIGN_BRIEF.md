# Lab Builder Map-First Redesign — build brief for Codex

Status: approved by Steve (CXO relaying)
Depends on: `LAB_BUILDER_SIMPLICITY_CONTRACT.md` (incl. Amendment 1: Navigation Spine),
`LAB_BUILDER_IA_ALIGNMENT_BRIEF.md`
Visual reference (design mockup): https://claude.ai/code/artifact/aae929b5-c565-48bd-b5ff-4a98cbaee824

This brief is the design spec for three operator surfaces inside the 5173 product
(`infra-config-portal`): a map-first Overview, a concise defaults surface, and a radically
simpler firmware page. Match the mockup's structure and copy intent; use the app's real
components and data. Do not import any code from the `lab-builder` (8011) app.

## Decision on placement

The settings/defaults surface is named **"Lab Defaults"** and lives as the **first module inside
the Setup phase** (`/setup/defaults`), not a fourth top-level tab. This keeps the three-phase
spine (Overview / Setup / Run) from Amendment 1 intact. (Reversible to a top-level tab only on an
explicit later call from Steve.)

## Surface 1 — Map-first Overview (`/overview`)

The topology map is the hero: the first and largest object on the page. Readiness, blockers, and
the one next action sit in a narrow right rail, never above the map.

- **Layout:** two columns — dominant map card (left) + narrow right rail. Under ~1080px the rail
  drops beneath the map. The map gets its own horizontal-scroll container so the page body never
  scrolls sideways.
- **Map card:** header (`Lab topology` + `N devices · subnet <cidr>` + a runtime pill, e.g.
  `TEST MODE · NO HARDWARE TOUCHED` in amber, or a live variant); a staged canvas with two labeled
  zone bands (**Management network** / **Storage & compute**) matching the existing
  `zone: "management" | "storage"` data; the real device nodes (Cisco Switch, HPE iLO, vCenter,
  HPE Gen10, NetApp ONTAP, Datastore), each with an icon, a status LED, a `READY / BLOCKED /
  NOT CHECKED` label, and a mono meta line (IP, or "not mounted"); cable links colored by status
  (solid green = ready, dashed grey = not checked, dotted red = blocked); a legend for the three
  states.
- **Right rail (the four-question budget):**
  1. **Current state** — e.g. `1 device blocked`, a one-line plain message, and a segmented
     readiness meter (`2 / 6 ready`).
  2. **Next action** — one primary button, phase-aware copy (e.g. `Fix the compute sign-in`);
     a quiet secondary `View all device details` link.
  3. **Needs your attention** — plain-language blockers ("Username or password is missing, so the
     host can't be reached. Fix it in Setup › Compute & iLO."). Not-checked items explain they stay
     grey until unblocked, so the operator knows there's nothing to do there yet.
- **Honest states:** unknown -> `NOT CHECKED` (hollow LED), never fake green.
- **Spine fit:** this *is* Overview. It does **not** render the build step list (that stays in Run
  Center per Amendment 1). One primary action only.

## Surface 2 — Lab Defaults (`/setup/defaults`, first module under Setup)

Concise, no sprawl. Three cards:
- **Network** — subnet / gateway / DNS.
- **Shared sign-in** — username + password, each with a `Saved` / `Not set` chip. The actual
  secret is entered on the device page, **not here** — keep credential entry off this surface.
- **Expected devices** — a list with a per-device toggle; turning one off removes it from the map
  and the build.
- Subtitle: "Shared values this kit reuses everywhere. Set them once here instead of retyping them
  on every device page." One primary action: **Save defaults**, with the reassurance "Nothing is
  sent to hardware from this page."

## Surface 3 — Firmware table (`/setup/firmware`)

Replace the current dense firmware map/compliance/lanes/evidence UI **entirely** (replace, don't
add). A plain table, one row per device, exactly four columns:

- **Device** — icon + name + role.
- **Current version** — mono.
- **Target version** — mono, with `->` and a small hint (`upgrade available` / `already current` /
  `scan to compare`).
- **Action** — two controls: **Upgrade** (accent, primary) and **Bypass** (quiet). Upgrade is
  disabled when already current or not yet scanned. Choosing collapses the cell to a
  `Upgrade queued` / `Bypassed — left as-is` pill with an **undo**.
- Footer line: "Upgrade asks you to confirm before it touches real hardware. Bypass leaves the
  device as-is and records the choice." No logs or payloads on the operator view.

## Guardrails (hard limits)

- Operator vocabulary only — no `provider`, `runtime`, `payload`, `env mode`, or `PROVIDER_MODE`
  in any operator-tier copy, including blockers.
- Do not weaken or invoke any destructive/live-hardware gate. Upgrade stays gated; the iSCSI
  datastore stays read-only validation (`esxi.iscsi-datastore-validate` / `read_only`).
- Keep the build engine and the map's underlying data model intact; this is presentation + copy.
- Navigation stays the three-phase spine; Lab Defaults lives inside Setup.
- Responsive: no horizontal body scroll at 375px; map has its own scroll container; header stays
  compact (fluid `auto-fit` grids, `clamp()` type).
- Design grounded in: `app/frontend/src/components/operator/OperatorHomeView.tsx`, the
  `LabTopologyMap` (nodes/zones, `operatorPages.tsx` ~line 5915), and the firmware map
  (`operatorPages.tsx` ~line 4247).

## Suggested slices (return each for CXO review before the next)

1. **Map-first Overview** — the priority. Map as hero + right rail (four-question budget, one next
   action). Overview stops rendering the build step list.
2. **Firmware table** — replace the dense firmware page with the four-column Upgrade/Bypass table.
3. **Lab Defaults** — the three-card defaults surface as the first Setup module.

## Acceptance tests

1. On Overview, the map is the first and largest element and renders the real device nodes with
   `ready / blocked / not checked` states; unknown never renders as green.
2. Overview does not render the build step list and has exactly one primary action.
3. No operator-tier string (including blockers) contains banned vocabulary (assert absence of
   `PROVIDER_MODE`, `provider`, `runtime`, `payload`).
4. Firmware renders exactly the four columns; Upgrade is disabled when current/unscanned; Bypass
   records the choice; the old firmware map is gone (replace, not add); no logs on the operator
   view.
5. Lab Defaults renders inside Setup as the first module; the credential secret is not entered on
   this page; a single Save defaults action exists.
6. Responsive: no horizontal body scroll at 375px; the map has its own horizontal-scroll
   container.
7. Existing build-engine, guarded-gate, and iSCSI read-only tests still pass unchanged.

## Do not do

- Do not import `lab-builder` (8011) code.
- Do not add navigation beyond the three-phase spine.
- Do not rebuild the build engine or the map's data model.
- Do not put developer vocabulary or raw logs on any operator surface.
