# Lab Builder — Functional Test Plan (Claude, live real-lab pass)

Branch: `unified-build-journey`. Runtime pair: frontend `127.0.0.1:5175`, backend `127.0.0.1:8002`,
`provider_mode=local-lab-readwrite`, `operator_runtime_mode=real_lab`.

## Ground rules

- **Non-destructive, extensively, continuously.** Every read, every save, every read-only workflow
  action (reachability/auth/inventory/preview-only checks) is in scope without asking first.
- **Destructive or hardware-reconfiguring actions get a checkpoint, always.** RAID apply/reset/rebuild,
  factory reset, firmware update/flash, NetApp/iSCSI writes, ESXi reinstall, power actions, one-time
  boot, virtual media insert. The permissive flags in the private env
  (`LAB_ALLOW_POWER_ACTIONS`/`LAB_ALLOW_FIRMWARE_UPDATES`/`LAB_ALLOW_FACTORY_RESET`) are not treated as
  standing authorization — each specific action gets its own confirmation before it runs.
- **Every fix gets verified live**, not assumed from reading code: reproduce the bug first with
  evidence (network request, DOM state, or backend response), fix, then re-verify the same way.
- **Every fix gets a regression test** where the codebase has a test suite for that layer.

## Sequence

1. **Address/credential source-of-truth pass** (in progress) — resolve every device where the
   env-var override target and the saved-profile address disagree, the way the iLO
   `10.10.8.110` vs `192.168.1.201` mismatch was resolved. Check ESXi, Cisco, NetApp, vCenter the
   same way (`*_TEST_HOST` / target env vars vs `address_plan`).
2. **Device-by-device functional audit** (per page, live against real backend):
   - Overview map: all device drawers, save round-trips, reachability status accuracy vs actual
     evidence (Codex flagged Cisco/ESXi/NetApp status labels showing "ready" without current
     evidence — needs its own investigation).
   - Compute & iLO (`/setup/ilo`): Main settings save (fixed), RAID planner, tab strip, credentials
     panel host fields (new).
   - Storage & NetApp (`/setup/storage`), Network/Cisco (`/setup/cisco`), Virtualization
     (`/setup/esxi`): same save-round-trip and drift-detection audit as iLO, since the iLO bug's root
     cause (bucket-precedence in shared draft-commit code) may affect these pages' equivalent fields
     too — check ESXi/Cisco/NetApp "Main settings" fields specifically for the same class of bug.
   - Lab Defaults, Firmware, Run Center, Reports/Validation, Media, Saved Kits, Requests — functional
     pass: every button does what it says, every save persists, no console errors, no silently-eaten
     backend errors (422/500 shown only in easy-to-miss inline text, like the profile_topology bug).
3. **Known live backend errors** (from Codex's handoff, still open):
   - `GET /api/v1/providers/ilo-redfish/esxi-install-readiness` → 500 (`httpx.ConnectTimeout`)
   - `GET /api/v1/providers/ilo-redfish/hpe-raid-pending` → 500
   - Both fire repeatedly while workspace pages load — likely unhandled-timeout bugs in those read
     paths, not "device is just offline" (a slow/unreachable device should surface as a normal
     failed-status response, not an unhandled 500). Fix the exception handling.
4. **Status-label honesty pass** — Codex flagged `cisco-console`/`cisco-ansible`/`esxi-readonly`
   reporting `ready` while their evidence is `not_checked/unknown` and `is_current=false`. Find where
   that label gets set and make it require current evidence, matching the "never paint ready without
   current target-bound proof" rule already applied elsewhere in this app.
5. **Report** — running list of bugs found/fixed with live-verification evidence for each, plus
   anything found that needs Steve directly (hardware/network issues, ambiguous behavior, anything
   destructive).

## Out of scope for this pass (explicitly deferred, not forgotten)

- Any actual RAID/firmware/factory-reset/power/boot/virtual-media action.
- Deep HPE Redfish OEM-path validation across iLO 5 vs iLO 6, and ESXi 7 vs 8 API differences — this
  needs real per-generation hardware access to validate properly rather than guessing from docs; will
  pick up once read-only connectivity is confirmed working end to end.
