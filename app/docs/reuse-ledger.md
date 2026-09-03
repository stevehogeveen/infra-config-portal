# Reuse ledger — check before you build

MUST: before building anything, both agents check this ledger AND the existing code, then reuse or extend what's here — never rebuild something that already exists. When you build something reusable, add it here in the same change.

Why: two agents on one codebase duplicate work fast. This is our dedupe.

## Reusable components (frontend)
- Parametric faceplate — renders any device from existing params (`drive_bays`, `ports`, `controller_ports`, RAID, VLAN, protocol). Use for every device type; don't hand-draw device art.
- `TopologyMapNodeCard` — the zoned-map node card. Reuse for any node on the map.
- Luminous control-room topology layout — radial map surface using the existing `TopologyMapNodeCard`, honest-state tone classes, zone metadata, and center `TopologyCoreButton`. Reuse/extend this layout for map polish; don't reintroduce fixed-slot band layouts or duplicate node cards.
- `SystemSetupStrip/Panel` — the top-center Living Topology setup picker. Reuse it for active lab-profile selection and subnet-derived IP planning; do not add another setup/history header or duplicate profile switcher. Visual tokens: compact anchored white panel, 16px radius, `0 12px 34px rgba(40, 60, 120, 0.12)`, teal `#14b8a6`, indigo `#6366f1`, dashed planned-IP panel, amber planned tags.
- Device workspace overlay (M6) — the click-open right-side drawer for deep editing. This is THE escalation surface; route all deep detail here, don't spawn new panels.
- Grouped device-workspace controls + guarded boundary notes — accepted pattern for moving page run-controls into a device workspace. Group read-only checks, setup previews, and validations; keep guarded writes/destructive actions visually separated or on Validation. Reuse for device parity slices instead of adding flat button walls.
- Physical element inspector (M7) — click a faceplate port/bay/controller → inline inspector mapped to schema fields. Extend it for new element types.
- Three-way state chips with provenance (M8) — Live/Draft/Saved with a source label. Use everywhere state is shown; don't invent new status UI.
- Schema-home inventory panel (M3) — shows the persistence path per field. Reuse to prove any field's schema home.
- Zone auto-layout (management / storage bands, zoom/pan/fit) — the scalable map layout. Place nodes by `zone`; never re-add fixed positions.
- `PageIntentBar` + page region manifests — Tier 1 in-app AI layout layer. Reuse this for page-level hide/show/collapse/reorder only; every page must declare an allowlisted region manifest and persist reversible layout state per profile.
- UI atoms: `status-badge`, `blocker-item`, `action-link`, `compact-table`, `card`, `remediation-ladder`.

## Reusable logic / backend
- Read-only workflow-action API + resolver + probes — all live/test data comes through these. Don't add parallel data paths.
- Evidence artifacts + review packet + persistence round-trip.
- Deployment modes + `lab_topology` subnet+offset address derivation.
- Honest-state rule — neutral/unknown by default; green only from real evidence.
- Offline ESXi installer artifact builder — reuse `esxi_installer_artifact.py` for profile/fingerprint-bound Kickstart media preparation. It snapshots rather than modifies source media, refuses plaintext/`firstdisk`, uses xorriso boot-equipment replay, reads back BIOS+UEFI config and Kickstart, and publishes only content-addressed checksummed artifacts. It never contacts hardware and is not an install executor.
- Exact-target iLO write context — reuse `IloWriteTargetContext`, `resolve_ilo_write_target_context`, and `refresh_ilo_write_target_context` for every iLO-backed mutation. Require one explicit current-access IP, fresh authenticated single-target evidence, hardware identity plus evidence digest, no fallbacks, and an immediate identity refresh before writing.
- Exact-target local-storage discovery — `raid.discovery` must receive the operator-selected `ilo_host`, use no fallback candidate, and never unlock cached bay inventory from another target.
- Resource-aware Redfish drive identity — keep the Redfish `@odata.id` as the stable inventory selection key when iLO omits controller-port/box/bay data. Show the discovered drive and its live logical-drive/spare membership, but block recommendation/apply payloads until the controller exposes a write-compatible physical location.
- Runtime cache isolation for tests — backend tests must use the autouse temporary `probe_cache.CACHE_DIR` fixture and clear in-memory provider results before/after each case. Never let mocked provider evidence reach the real runtime cache or make the live map green.
- Build-start evidence boundary — reuse `BUILD_START_EVIDENCE_REQUIREMENTS`: current profile-bound Cisco intent, exact-current-address iLO reachability, and RAID validation are pre-run requirements. The build begins at guarded ESXi installer boot; do not reinsert iLO, RAID, or switch bootstrap into Run.
- UI intent resolver — Tier 1 Claude/Anthropic primary interpreter with deterministic local fallback. Returned ops must be validated against the page manifest and allowlisted layout ops only.
- AI change-request queue — Tier 2 capture-only endpoint writes reviewable markdown into `docs/change-requests/`. Reuse it for non-layout in-app AI asks; it must never execute code, run workflow actions, or auto-apply changes.

## Safety machinery — reuse, NEVER rebuild or weaken
- Guarded workflows and the RAID-apply / factory-reset / rebuild confirmation gates. Keep exactly as-is; nothing bypasses them.

## Capabilities — don't hand-roll what a tool already does
- Claude has skills: `/code-review` (bug review of a diff), `/verify` (run the app and confirm behavior), `/simplify` (reuse + cleanup pass). Use them instead of ad-hoc equivalents.
- Codex: reuse the existing test harness (`scripts/fast-verify.ps1`, the Playwright suite) rather than new one-off checks.

Add new reusable pieces here the moment you build them.
