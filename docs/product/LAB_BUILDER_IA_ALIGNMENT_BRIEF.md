# Lab Builder IA Alignment — bring the `lab-builder` (8011) shell into `infra-config-portal` (5173)

Status: proposed (CXO alignment brief for Codex)
Depends on: `docs/product/LAB_BUILDER_SIMPLICITY_CONTRACT.md` (see Amendment 1: Navigation Spine)
Reference app: the separate `lab-builder` server-rendered app (port 8011) — structure only, do
not merge its code.

## Decision

`infra-config-portal` (the 5173 React app) is the go-forward Lab Builder product. There were two
same-named projects on different ports; this consolidates onto 5173. Keep everything 5173 already
does well and bring the *structure* of the 8011 app into it. The 8011 app is a reference for
information architecture, not a codebase to import.

## Keep (5173 assets — do not rebuild)

- The unified build engine and the Build Plan -> Run Console -> Completion journey (PR #4,
  already reviewed and approved). It moves into the new Run Center unchanged.
- The topology map. It stays on the Operator Home dashboard.
- The Operator Home simplicity model and the Simplicity Contract.
- Every device capability, guarded/destructive gate, and the read-only iSCSI boundary
  (`esxi.iscsi-datastore-validate` / `read_only`).

## Bring in from the 8011 app (structure)

1. A left **navigation spine** with three phases (replaces the thin Overview/Firmware/Validate
   top nav):
   - **Overview** — the dashboard: status + topology map + one phase-aware next action.
   - **Setup** — the setup modules: iLO, Storage, ESXi, Windows, Cisco, NetApp, OVF, plus
     Firmware and Global (shared defaults). Each is a Details-tier setup surface.
   - **Run** — Run Center (the build journey) and Reports (the existing validation/proof view).
2. **Kit management** — create a new kit and switch between saved kits, surfaced in the spine
   header. This is the Choose-Kit front door 5173 lacked.
3. **Plain-language blockers**, modelled on the 8011 copy: "Username or password is missing." +
   "How to fix it: open the iLO page and save the username and password." This replaces the
   current `PROVIDER_MODE=...` leak on Operator Home.
4. Optional operator affordances: the Ctrl-K command palette and the compact-view toggle.

## Target information architecture (routes)

- `/overview` — Operator Home. Status, map, one next action. Does NOT render the build step
  list (that now lives in Run Center). Next action is phase-aware: if setup is incomplete it
  routes to the relevant Setup module; if setup is complete it routes to Run Center.
- Setup modules (Details tier), e.g. `/setup/ilo`, `/setup/storage`, `/setup/esxi`,
  `/setup/windows`, `/setup/cisco`, `/setup/netapp`, `/setup/ovf`, `/setup/firmware`,
  `/setup/global`. (Reuse existing 5173 setup surfaces; do not invent new device types.)
- `/run` — Run Center. Hosts the existing LabBuildJourney (Build Plan -> Run Console ->
  Completion). This is where the ordered steps and Start Build live.
- `/reports` — the existing validation/proof surface.

## Reconciliation with the Simplicity Contract

This adds navigation, which the original contract forbade. That rule is being amended on
purpose, not broken — see `LAB_BUILDER_SIMPLICITY_CONTRACT.md` Amendment 1 (Navigation Spine).
The amendment permits exactly the fixed three-phase spine (Overview / Setup / Run) plus the
setup-module list inside Setup and the run surfaces inside Run. Everything else in the contract
still holds: the four-question budget on Operator Home, one primary action, one fact/one owner,
operator vocabulary, exceptions over inventory, replace-don't-add, the five-second test.

## Guardrails (hard limits)

- No new device types. No orchestration studio. No user-editable dependency graph.
- Navigation is limited to the three-phase spine + setup modules (in Setup) + run surfaces
  (in Run). No ad-hoc tabs, and no per-device surface bleeding onto Operator Home.
- No developer vocabulary (provider, runtime, payload, env mode, `PROVIDER_MODE`) in any
  operator-tier copy, including blockers.
- Do not weaken or invoke any destructive/live-hardware gate; keep iSCSI read-only.
- Replace, don't add: when a spine/Run surface lands, remove the superseded top nav and the
  in-place build-journey swap on `/overview`.

## Suggested slices (keep each boring and reviewable)

1. Spine + kit management: three-phase sidebar, kit create/switch, Operator Home keeps status +
   map and drops the step list.
2. Setup modules: route each device/setup surface under Setup; adopt the plain-language blocker
   copy (kills the `PROVIDER_MODE` leak).
3. Run Center: move the build journey to `/run`; `/overview` no longer swaps it in; Reports
   under Run.
4. Responsive + affordances: fluid `auto-fit` grids, compact wrapping header, `clamp()` type;
   optional Ctrl-K palette and compact-view toggle.

## Acceptance tests

1. The spine renders exactly three phases (Overview / Setup / Run); the Setup list contains the
   device/setup modules; Run Center is reachable.
2. Operator Home does not render the build step list; the step list appears only in Run Center.
3. Kit create and switch work and update the selected kit across every surface.
4. No operator-tier string (including blockers) contains banned vocabulary (assert absence of
   `PROVIDER_MODE`, `provider`, `runtime`, `payload`, `env mode`).
5. The topology map renders on Operator Home.
6. Layout quality: no horizontal overflow at 375px; header height capped at 375px; the blocker
   grid renders multiple columns at >= 900px.
7. The build-journey engine tests and the guarded/iSCSI-boundary tests still pass unchanged.

## Do not do

- Do not import `lab-builder` (8011) code; it is a structural reference only.
- Do not rebuild the 5173 build engine or map.
- Do not add navigation beyond the three-phase spine.
- Do not keep both the old top nav and the new spine (replace, don't add).
