# Claude Review Packet

## Current Status

M1 schema-home audit is complete.

- `devices.server_model` is a real committed profile field with allowed values `gen10` and `gen10plus`.
- The visual builder commit payload writes `devices.server_model`.
- Backend schema accepts `gen10` / `gen10plus` and rejects unknown values.
- Topology normalization preserves `server_model`.
- Overview design defaults read `activeProfile.devices.server_model`, so DL360 Gen10+ survives commit -> reload.
- Playwright commits DL360 Gen10+, reloads, sees DL360 Gen10+ still in Rack A, and sees `Draft matches profile`.

M2 reversible visual slice is complete.

- Parametric faceplates render from existing params: `drive_bays`, `ports`, `controller_ports`, RAID, VLAN, and protocol.
- Server bays, switch ports, NetApp controller ports, LEDs, and chips are visual, draft-only, and driven by fields already allowed in `device_settings`.
- Review packet includes `server_model`.
- Profile sync preview has a first-class Server model row.

M3 schema inventory slice is in progress/green in focused tests.

- Each selected device editor now shows a `Schema homes` panel generated from the same field list as the visible inputs.
- Rows show draft persistence paths such as `device_settings.switch.management_ip`.
- Rows that commit into the lab profile show the profile destination, for example `address_plan.cisco_management` and `devices.server_model`.
- Focused overview design-mode Playwright checks now assert the switch schema inventory and Gen10+ `devices.server_model` row.

M4 subnet mobility slice is in progress/green in focused tests.

- The design composer now shows host-network evidence inside the subnet rebase area.
- When this Windows machine is on a different subnet than the saved profile, the composer shows the mismatch and host IPv4 addresses.
- Operators can stage the detected host `/24` as a draft subnet, rebase addresses, then commit profile intent separately.
- This remains draft-only; it does not update runtime env or touch hardware.

M5 visual topology control strip is complete.

- Design mode now has a compact `Topology draft controls` strip above the blueprint.
- It summarizes scenario, storage protocol, draft persistence, profile sync drift, selected device, and subnet.
- The selected-device tile updates when operators click nodes, address rows, cabling rows, or faceplates.
- A secondary `Commit visual draft` button is available from the visual surface; the existing plan-panel commit button remains.
- The strip is wired only to existing persisted draft/profile state. No new unschematized knobs were exposed.
- Claude CLI review approved the slice and flagged two fixes, both applied:
  - selected-device tile now focuses the real device editor and posts an operator-visible message instead of being a no-op.
  - both commit buttons now share drift-aware labels and refuse no-op profile writes when the draft already matches profile intent.

M6 click-first Device Workspace shell is complete.

- Clicking a topology device now opens a dedicated right-side workspace while the dark canvas stays visible for context.
- The selected node lifts/glows and other nodes recede, so the clicked device becomes the product focus.
- Workspace identity bar shows name, model, role, three-way state (`Live` / `Draft` / `Saved` style), reachability, and one primary read-only test action.
- Hero faceplates are interactive: switch ports, server bays, NetApp controller ports, and VM chips are clickable and post operator-visible draft messages.
- Parameters are grouped by intent: Identity, Network, Storage, Access. Inline controls expose draft/saved/live state copy without showing secrets.
- Device-scoped safe checks and next actions are inside the workspace, wired only to existing read-only workflow actions.
- Schema inventory moved into the device workspace tests: switch `Management IP` and Gen10+ `devices.server_model` are both asserted from the selected workspace.
- The canvas stretch bug is fixed: the workspace no longer forces the topology canvas to 2048px tall.
- No RAID apply, factory reset, rebuild, or other destructive gate is reachable from this workspace slice.

M7 physical element inspector slice is complete.

- Claude's review steered the next slice away from broad drag/drop and toward deepening the click model one level down.
- Clicking a faceplate element now opens an inline inspector for that exact element:
  - switch ports map to `device_settings.switch.ports`, `port_profiles`, VLAN intent, and read-only workflow proof.
  - server drive bays map to `drive_bays`, `raid_controller`, `raid_boot`, and `raid_data`.
  - NetApp controller ports map to `controller_ports`, protocol, NFS LIFs, and iSCSI LIFs.
  - vCenter/Windows elements map to their existing VM/network role fields.
- The inspector names the persisted source for every row and states the guardrail clearly.
- It is a frontend/read-only inspector only. It adds no new schema knobs and no write/destructive path.
- Selected element state resets per selected device so a server does not inherit a switch-port inspector.
- Playwright now clicks `Switch port 1` and `Drive bay 1` and asserts the inspector maps to existing fields.

M8 state provenance slice is complete.

- Claude flagged the wording `Live-Draft-Saved style state` as a correctness risk: state must be real data, not cosmetic status.
- Each state chip now renders its source directly below the chip:
  - draft state sources: unsaved browser edit, profile drift, persisted design draft, loading draft store, browser fallback, or local draft defaults.
  - reachability sources: last read-only workflow action, no registered proof, or no read-only run yet.
- Playwright now asserts the source labels before and after running the Cisco Firmware Inventory read-only action.
- After the action, reachability must read from `source: last Cisco Firmware Inventory`.
- This makes fake-green harder to accidentally introduce because the visible state has to name its evidence source.

M9 honesty audit follow-up is complete/in progress.

- Five-point state-honesty audit result:
  - Three-way state is not static styling. It is derived from real draft dirty state, profile drift count, and persisted draft-store state. Saved only appears when draft persistence is `persisted` and profile drift is zero.
  - Reachability defaults to `Reachability unknown` with `source: no read-only run yet` until an action run exists.
  - Faceplate LEDs no longer use green `ready` styling by default. They render neutral/plan/draft until element-level evidence is wired.
  - Editable parameters have schema-home inventory. Profile-writing fields show commit destinations; fields without a profile destination are labeled `Draft-only visual intent`.
  - `devices.server_model` round-trips through commit -> reload and is asserted in Playwright.
- Mode distinction follow-up:
  - Single-server mode now has explicit test coverage for the canvas archetype chip (`Single server - local RAID` / `Sparse local mode`).
  - Single-server visual blueprint must omit NetApp and vCenter nodes.
  - Server workspace storage section must show local RAID layout and `RAID6 local datastore`.

ZONES M1 zoned canvas shell is complete.

- Branch: `zones-map-home`.
- Baseline checkpoint commit: `7ae3ce6 chore: checkpoint pre-zones operator work`.
- The Overview home map now renders as a zoned canvas instead of the older freeform topology:
  - top band: `Management` with vCenter + Cisco switch.
  - bottom band: `Storage fabric` with HPE server + NetApp.
  - mode chip: `Server + NetApp + vCenter` or `Single server - local RAID`.
  - nodes render as faceplate cards using the existing parametric faceplate component.
  - cables are drawn through the zones with protocol/speed labels (`mgmt 1G`, `storage VLAN`, `NFS 10G path` / `iSCSI 10G planned`).
- Honest-state rule carried through:
  - faceplate LEDs stay neutral/unknown by default.
  - ready-count copy says `checks ready`, not `checks green`.
  - no new write/destructive path was added.
- E2E now asserts the zoned home map is visible, includes Management/Storage fabric, shows vCenter/switch/server/NetApp, and draws the storage path label.
- M6 workspace remains available behind Design/Open workspace; this milestone does not delete old panels yet. M4 will retire dead surfaces after the map owns node/system interactions.

ZONES M1 verification:

- `npm run build`: pass.
- `scripts/fast-verify.ps1`: pass, including frontend build, component test, and focused overview design Playwright `4/4`.

ZONES M2 node/system map controls are complete.

- The zoned canvas is now an interaction surface, not just a visual:
  - clicking a device card opens a node-scoped menu.
  - node menu actions: `Set deployment mode`, `Assign IP block`, `Run test (read-only)`, `Switch profile`, and `Open workspace`.
  - `Open workspace` escalates into the M6 device workspace with the clicked device selected.
  - `Run test (read-only)` uses the existing workflow action API and refuses anything outside `read_only` / `report_only` mode.
- The deployment mode chip now opens a system-scope menu:
  - deployment mode, site subnet, active/switch profile, and validation.
  - this keeps system-level changes on the map instead of a separate overview surface.
- Guardrails carried through:
  - no RAID apply, factory reset, or rebuild flow was added.
  - destructive/write actions are blocked from the zoned map runner.
  - all deep editing still lands in the existing M6 workspace/persistence model.
- Test caught and fixed a real canvas issue:
  - the node menu initially opened under another faceplate card, which intercepted the click.
  - selected nodes now lift above the canvas stack while their menu is open.

ZONES M2 verification:

- `npm run build`: pass.
- `npm run test:e2e -- -g "zoned map opens node"`: pass.
- `scripts/fast-verify.ps1`: pass, including frontend build, component test, and focused overview design Playwright `4/4`.

Next planned slice:

- ZONES M3: make the zones mode-adaptive and unmistakable:
  - `Single server - local RAID` collapses/removes NetApp + vCenter from the map and makes the server/local RAID faceplate the hero.
  - `Server + NetApp + vCenter` populates both bands with explicit storage fabric and datastore path.
  - workspace Storage section adapts cleanly between RAID-local and NetApp datastore.
  - keep this frontend/reversible only; no destructive gates.

## Verification

- `npm run build`: pass.
- Overview design-mode Playwright slice: 4/4 pass after visual snapshot review/update.
- Full `scripts/fast-verify.ps1`: pass three times after M6/M7/M8, including 33/33 Playwright, 80 backend API tests, workflow diagnosis, OpenAPI, QA audit, and Windows script tests.

No RAID apply, factory reset, or rebuild gates were touched.

## Request For Claude

Codex is continuing autonomously on the ZONES direction. Please review M2 cheaply from this packet:

- Is the node menu scope right, or should any action move elsewhere before M3?
- Does `Open workspace` into M6 feel like the right escalation model?
- For M3, what is the clearest visual treatment for making `Single server - local RAID` unmistakably different from `Server + NetApp + vCenter` without adding clutter?
- Hidden correctness risk to watch: any canvas option that looks saveable must have a schema home and must round-trip; any live/reachability cue must come from real probe evidence.
