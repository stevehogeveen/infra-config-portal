# Tier 1 — in-app AI intent bar (instant, reversible, no code)

Goal: on each page, Steve says "remove this clutter / hide this / collapse advanced / simplify this" and the page changes IMMEDIATELY, reversibly, with no code change and no risk. This is the layout/visibility layer of the in-app AI. Tier 2 (real code changes routed to the Claude+Codex loop) comes later.

Sequence: start this AFTER the current design-map polish pass lands. Don't interrupt the polish.

MUST first: check `reuse-ledger.md` and existing code. Reuse the existing panel/card components and any current collapse/visibility state — do not build a new panel system.

## What it is
A small "Change this page" input on every operator page + the map. Natural-language request in → the page's layout adjusts (hide / show / collapse / expand / reorder pre-declared regions) → instant, with Undo and Reset.

## Hard boundary (non-negotiable)
The intent bar can ONLY change presentation of pre-declared page regions. It can NOT change data, run workflow actions, alter settings, or touch code. Zero path to RAID / factory / rebuild or any write. Pure, reversible layout.

## Data model
- Each page declares a REGION MANIFEST: `{ id, label, kind: panel|drawer|section|row, defaultVisible, collapsible }` for the regions the AI may toggle. This is the allowlist — the AI can act on these ids only.
- A per-page LAYOUT STATE: `{ regionId: { visible, collapsed, order } }`, persisted (per active profile / localStorage) so changes stick across reload. Includes `reset` to defaults.

## Backend endpoint
`POST /api/v1/ui-intent`
- body: `{ page, request, regions: [{id,label,kind}], currentLayout }`
- Calls the Claude API with STRUCTURED OUTPUT constrained to: `{ ops: [{ regionId, op: "hide"|"show"|"collapse"|"expand"|"moveUp"|"moveDown" }], summary }`.
- Model: `claude-opus-4-8` by default; a lighter model is fine here (constrained classification) if cost matters — Steve's call.
- Validate every returned `regionId` against the manifest; drop anything unknown. Never trust free-form output.
- API key: `ANTHROPIC_API_KEY` from a gitignored env (same secret discipline as lab creds — never committed, never shown in the UI). Run any payload through the existing redaction path before it leaves the box.

## Frontend
- `<PageIntentBar page=... regions=...>` on each page: one small input + a tiny "what changed" line + Undo + Reset.
- On submit → call `/api/v1/ui-intent` → apply ops to layout state → persist → show "Hid: Advanced proof, Firmware panel. Undo?".
- Undo reverts the last op set; Reset restores page defaults.
- The bar states plainly that it only rearranges this page and changes nothing else.

## First targets
Overview/design map + one busy operator page (e.g. Storage) to prove the pattern, then roll to the rest.

## Done =
- Say "remove this clutter" on a page → the declared clutter regions hide instantly, persist across reload, Undo works, nothing else changes.
- No data / action / code / gate reachable from the bar.
- Reversible-only, commit + fast-verify green, update the review packet + reuse-ledger.
