# Rack workspace redesign — design reference

Self-contained mockups from the 2026-08-12 design session. Open any `.html` in a browser
(no build step, no dependencies, no network calls). PNGs are renders of the same pages for
anyone who cannot run a browser.

These are **design references, not application code.** Nothing here imports from `app/frontend`
and nothing in the app imports from here.

| File | What it shows |
| --- | --- |
| `01-dashboard-concept.html` | The approved direction: three columns — Metal (rack) / Software (per-server) / Cluster. Today's real state: nothing installed, vSAN not formed. |
| `02-dashboard-built-state.html` | **The layout Steve picked as the dashboard.** Same frame once the build exists: the 2-drive ESXi boot pair, three storage types, vCenter as a VM, VM chips on hosts. |
| `03-deeper-visuals.html` | Four developments of it — the same screen at four build stages, the drive-allocation panel, VM placement, and the vCenter deploy order. |
| `04-build-flow.html` | **Interactive.** The seven-question flow: what you're building, which servers (including ones the app has never met), addresses, management, storage, drives, review. Click through it. |
| `05-blend-options.html` | Three ways to reconcile this with the separate Strata configurator prototype. Option B (Design mode + Build mode) was recommended; **not yet decided.** |

## Things to try in `04-build-flow.html`

- Question 2 → **+ Add a server Lab Builder has never met** → name, address, iLO UID, password →
  **Run first contact**. Its model and bay count stay unknown until it replies.
- The **Preview outcome** dropdown next to an added server switches between success and the seven
  real failure classifications. It is a design control only — real contact decides its own outcome.
- Question 3 — ESXi addresses start blank on purpose. Each field states where its value came from:
  proven / saved plan / blank / suggested.
- Drop to two servers on question 2, or set the subnet to `/25` on question 3, and watch storage
  options disable with the reason printed beside them.

## Rules these encode

1. Two drives per host are the ESXi boot pair (RAID 1). They never join vSAN. Every drive has
   exactly one job and the tally cannot exceed the probed bay count.
2. Green only ever appears next to a proof timestamp. A typed or suggested value is never green.
3. Nothing is invented for a device that has not answered — no model, no bay count, no drives.
4. Blocked options stay visible with their reason; they are never hidden.
5. A VM chip says where it runs; its colour swatch says where it is stored.

Full context is in the 2026-08-12 entry in `../agent-chat.md`.
