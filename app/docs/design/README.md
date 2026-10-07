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
| `06-density-redesign.html` | **Interactive.** 2026-09-25 proposal for full-screen density: a 1440 frame with a context rail, provenance chips instead of captions, one guard statement per screen, sized inputs, and results as banner plus table. Five screens; "Show what moved" traces every removed sentence. Includes a control-by-control map showing nothing is lost. **Proposal, not yet decided.** |
| `07-index.html` | 2026-09-25 comparison page for the six `07-` directions below, grouped by cohort. One card per direction: both judges' verdicts in a line each (novice lens and craft lens), average scores on seven dimensions, the designer's summary, what was left open after revision, and renders of My Rack and Add equipment (`07-<name>.png`, `07-<name>-build.png`). **Candidates for usability testing; not yet decided.** |
| `07-front-door.html` | **Interactive.** For non-IT users. Lab Builder as the companion app for a home appliance: warm surfaces, one verb-sentence button per screen, a plain-English line under every technical noun, a provenance chip on every value, and a CSS rack cabinet. Six screens including "When nothing answers". **Candidates for usability testing; not yet decided.** |
| `07-picture-book.html` | **Interactive.** For non-IT users. An illustrated instruction manual: ink outlines, one flat colour per kind of equipment, CSS pictograms, a rack drawn with feet, and timed green stickers only for proven values. Includes an "If it fails" screen with all seven failure kinds. **Candidates for usability testing; not yet decided.** |
| `07-companion.html` | **Interactive.** For non-IT users. A guided conversation: a narrator column with one button per state explains each provenance chip the first time it appears, beside the rack and forms it talks about. Includes a first-contact failure screen. **Candidates for usability testing; not yet decided.** |
| `07-instrument.html` | **Interactive.** Studio grade. A bench console: an LCD readout strip, an SVG rack elevation with a dimension line, embossed keys, a knurled rack-height stepper, and one signal red for primary keys and blocked reasons. **Candidates for usability testing; not yet decided.** |
| `07-blueprint.html` | **Interactive.** Studio grade. A drawing set in ink on vellum: numbered sheets with title blocks, a dimensioned rack elevation, a revision cloud around unsaved edits, and timed green rubber stamps as the only green. **Candidates for usability testing; not yet decided.** |
| `07-mission-control.html` | **Interactive.** Studio grade. An operations console: a status rail with the build steps and device lights, a Ctrl+K command palette, and an evidence drawer on every screen showing the last read-only check. Dark by default, with a designed light palette. **Candidates for usability testing; not yet decided.** |
| `08-lab-builder-blend.html` | **Interactive. Current direction (2026-09-25).** Lab Builder Studio: Steve asked to blend Mission Control, Companion and the original app, lighter than Mission Control, with complementary colours and strong graphics. Mission Control gives the build-steps rail with device lights, the evidence drawer and the Ctrl K palette; Companion gives one plain sentence and one orange button per screen and explains each label the first time; the app gives its own equipment art (web-sized copies in `08-assets/`), the white-metal rack and the orange, with deep ocean blue as its complement. Seven screens, including every storage outcome. Chosen from three candidate blends by a three-judge panel, then audited and fixed. **Proposal, not yet implemented.** |

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
