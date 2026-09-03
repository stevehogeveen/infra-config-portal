# 051 - vSAN Drive Readiness (Controller Mode + Passthrough Inventory)

## Goal

Steve is planning vSAN on the Uplands DL380. He needs the app to show whether
the drives can be made vSAN-ready — either via HBA/passthrough or a
vSAN-supported controller mode — and what the options are.

Live read-only evidence already gathered (2026-08-06, real box):
- Controller: HPE Smart Array P408i-a SR Gen10, firmware 1.66, hardware rev B.
- `CurrentOperatingMode: "Mixed"` — on Gen10 Smart Arrays, Mixed mode means
  RAID volumes and raw passthrough coexist: any physical drive NOT in a
  logical volume is presented raw to the OS. Full HBA mode also exists on
  this family (controller-wide, destructive to existing volumes, requires a
  config write + reboot).
- The controller resource does NOT advertise a `SupportedOperatingModes`
  list, and `smartstorageconfig`/`settings` expose no `OperatingMode` field
  on this firmware — so "supported modes" cannot be enumerated from Redfish
  here. Report what IS knowable: the current mode, and the two known paths
  (stay Mixed + keep drives unconfigured, or switch to HBA mode as a future
  guarded write). Do not fabricate a supported-modes list.

## Prerequisite inside this task: cross-view drive pairing

Per-drive vSAN readiness requires knowing which bays are in volumes. On the
DL380 the DMTF Storage view's volume `Links.Drives` reference
`/Systems/1/Storage/.../Drives/N` resources while the bay-bearing drives are
SmartStorage `DiskDrives` resources — direct `@odata.id` matching fails
(this is the known limitation flagged in the 047 review and the 050 packet).
Both views carry `hardware_identity_fingerprint_sha256` for the same
physical drive (verified identical across views on the DL360 live data).
Implement pairing through those fingerprints in the storage
discovery/readiness service so volume membership maps to physical bays.
This also unblocks the RAID planner's live seed on the DL380 — reuse the
same pairing in `localRaidLiveSeed`'s data source if it fits naturally, but
the vSAN panel is the priority.

## Scope

### Backend

A read-only vSAN readiness view over the cached storage discovery (follow
the existing pattern: derive from `probe_cache`/hpe-storage-discovery, no
new hardware contact in this task), e.g.
`GET /api/v1/providers/ilo-redfish/vsan-readiness`:

- Controller: model, firmware, `current_operating_mode`, and an honest
  `mode_meaning` string ("Mixed: drives outside RAID volumes pass through
  raw" / "HBA: all drives raw" / "RAID: no passthrough").
- Per physical bay (using the fingerprint pairing): bay id, capacity, media
  type, health, and `vsan_status`: `passthrough_ready` (not in any volume),
  `in_raid_volume` (blocked; name the volume), or `unknown` (pairing
  failed — never guess).
- Summary: counts + total capacity of passthrough-ready drives.
- Options list (informational, no actions enabled): stay-Mixed path
  (destructive volume deletion required for blocked drives, guarded, not
  yet available), HBA-mode switch (controller-wide, destructive, reboot,
  guarded, not yet available), and the VMware Compatibility Guide caveat
  (certification depends on ESXi build + driver/firmware; the app cannot
  verify it).
- `apply_enabled: false` everywhere. No write path of any kind.

### Frontend

A "vSAN readiness" section in the Local storage drawer (below the RAID
planner), read-only:
- Controller mode line with the meaning string.
- Bay grid or compact list showing each drive's vsan_status (reuse existing
  bay visual language from the RAID planner where possible).
- Summary line ("N drives / X TiB passthrough-ready for vSAN").
- The options as plain text with their guarded/destructive nature stated;
  no buttons that write.
- If discovery has no inventory yet, show the existing "run iLO inventory
  read first" guidance, not an empty panel.

## Explicitly Do NOT

- No hardware contact, no mode switching, no volume deletion, no new write
  or apply path. `PROVIDER_MODE=mock` for all Codex-run tests.
- Do not claim vSAN certification — only architecture readiness.
- Do not invent a supported-modes list the hardware does not report.
- Do not break the existing RAID planner or its live seed behavior.
- Do not touch `.env.local.real-lab` or `app/frontend/app/`.

## Tests

- Backend: fingerprint pairing (volume members map to bays through matching
  hardware fingerprints across views; unmatched drives come back `unknown`,
  never guessed); readiness derivation for a fixture with a boot volume + n
  unconfigured drives; a no-inventory fixture yields a
  "run discovery first" response, not fabricated data.
- e2e: storage drawer shows the vSAN section with mocked discovery (extend
  the existing hpeStorageDiscovery fixture — it pairs cleanly by @odata.id;
  add a DL380-style cross-view variant to prove fingerprint pairing renders
  correct statuses rather than all-unknown).
- Run backend pytest for the touched files + ruff; tsc/Playwright if your
  shell allows, otherwise say so and leave them to Claude.

## Docs

Mailbox entry in `app/docs/agent-chat.md`: endpoint shape, pairing
approach, and judgment calls.

## Leave Uncommitted

Claude reviews, runs full suites, verifies live against the Uplands box,
and commits.

## Addendum (Steve, mid-run 2026-08-06): server generations

The app must handle Gen10, Gen10+, Gen11, and Gen12 HPE servers. The fleet
already spans controller families: the 192.168.1.x DL360 reported an HPE
MR416i-a Gen10+ (MegaRAID family — DMTF Storage view only, no
HpeSmartStorage view, JBOD/EPD instead of Mixed/HBA modes), while the
Uplands DL380 Gen10 has the P408i-a Smart Array. vSAN readiness must not
assume the SmartStorage view exists: when only the DMTF Storage view is
present, derive readiness from it directly (volume membership pairing is
trivial there — one view), report the controller family honestly, and say
"mode options depend on this controller family" rather than assuming
Mixed/HBA semantics. If this lands after the initial 051 implementation,
it becomes the immediate follow-up slice.
