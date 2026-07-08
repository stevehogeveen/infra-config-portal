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

ZONES M3 mode-adaptive zones are complete.

- Active home map now makes the two deployment archetypes visually distinct:
  - shared mode keeps Management + Storage fabric populated with vCenter, switch, server, NetApp, datastore path.
  - single-server mode removes NetApp, vCenter, and the separate local-datastore node from the home map.
  - single-server mode shows a `Local RAID mode summary`: `Server-local RAID is the storage fabric`.
  - server card is the visual hero in local mode; storage is represented inside the server, not as a second pseudo-device.
- M6 design blueprint now mirrors the ZONES language:
  - management and storage/local bands appear in the design workbench.
  - local mode labels the lower band as `Local RAID inside server`.
  - local mode adds a one-server shipment summary below the server hero.
  - NetApp and vCenter remain absent in local-mode design unless deliberately added back through scenario/profile intent.
- Honesty cleanup:
  - the design blueprint device dot no longer defaults to green.
  - neutral gray indicates no live element evidence has been probed.
- Storage workspace behavior remains tied to existing schema/draft logic:
  - local mode still shows `Local RAID and drive layout` and `RAID6 local datastore`.
  - no new write/destructive path was added.

ZONES M3 verification:

- `npm run build`: pass.
- `npm run test:e2e -- -g "zoned map"`: pass, including node/system controls and single-server local RAID map distinction.
- `scripts/fast-verify.ps1`: pass, including frontend build, component test, and focused overview design Playwright `4/4`.

Next planned slice:

- ZONES M4: retire/delete the old overview surfaces now owned by the zoned map and tidy any selectors/routes that still depend on the superseded panels.
- Keep safety machinery intact: resolver, probes, persistence, evidence artifacts, guarded workflows, and all RAID/factory/rebuild confirmation gates stay untouched.

ZONES M4 overview retirement is complete.

- The Overview route now uses the zoned topology map as the focal/home surface.
- Removed the old rendered Overview reference stack from the route:
  - readiness stat cards.
  - provider cards.
  - setup lanes.
  - separate next-safe-actions panel.
  - separate firmware/blocker panels.
- Kept the important safety/proof surfaces:
  - guarded danger-zone link still points to Validation.
  - Lab Safety settings remain.
  - Advanced proof drawer remains for workspace rows, inventory, validation proof, and runtime facts.
- Tests now assert the retired panels are absent from Overview and the single-server story is owned by the map.
- Build output confirms the shipped JS bundle dropped after removing the render path.

ZONES M4 verification:

- `npm run build`: pass.
- `npm run test:e2e -- -g "overview shows active|overview retires|zoned map"`: pass `4/4`.
- `scripts/fast-verify.ps1`: pass, including frontend build, component test, and focused overview design Playwright `4/4`.

ZONES branch milestone commits:

- `7ae3ce6 chore: checkpoint pre-zones operator work`
- `eea48c0 feat: add zoned topology home shell`
- `f33542f feat: add zoned map control menus`
- `b5d4d18 feat: adapt zones map by deployment mode`
- `be2d8e1 feat: retire overview panels for zones home`

ZONES refinement from Claude/Steve feedback is complete.

- Addressed the two structural issues Claude called out:
  - clutter: Design mode no longer swaps the whole inline rack composer onto the page.
  - scalability: topology nodes no longer use hardcoded role slots like `cisco`, `server`, `netapp`, `datastore`, `vcenter`.
- Design mode now keeps the main surface map-only:
  - zoned bands, nodes, cables/link labels, mode chip, node dropdown, and map controls only.
  - no inline device hero, faceplate art editor, rack, parts shelf, or profile panels stacked below the map.
- M6 device workspace moved behind a right-side overlay:
  - clicking `Open workspace` opens the drawer.
  - the clicked node is selected in the real M6 workspace.
  - the map stays visible behind the overlay for context.
  - close returns to the clean map.
- Replaced fixed node placement with zone-based auto-layout:
  - `TopologyNode` now carries `zone: management | storage`.
  - Management and Storage fabric render as true auto-flow grid rows.
  - the rows handle additional devices without adding new hardcoded CSS position classes.
  - stale `.topology-node-cisco/server/netapp/...` positioning rules were removed.
- Added map viewport controls:
  - zoom in, zoom out, pan left, pan right, fit.
  - implemented as reversible frontend state only.
- Testing caught and fixed real hit-target bugs:
  - storage faceplate initially intercepted Cisco clicks.
  - Cisco faceplate then intercepted server clicks.
  - final fix made the map plane a true two-row grid instead of percentage-positioned bands.
- Guardrails:
  - no RAID apply, factory reset, rebuild gate, or backend safety machinery changed.
  - read-only/report-only guard remains on the map runner.
  - honest state and schema-home wording stay in the M6 workspace.

ZONES refinement verification:

- `npm run build`: pass.
- `npm run test:e2e -- -g "overview design mode"`: pass after updating the design-map snapshot.
- `scripts/fast-verify.ps1`: pass with full frontend E2E, `34/34` Playwright, component tests, and build.

ZONES visual polish pass is complete.

- Followed Claude's "one tight pass" guidance without adding new controls or behavior.
- Map toolbar is quieter and instrument-like:
  - compact `+ / - / 100% / Left / Right / Fit` control group.
  - subdued pill chrome and zoom readout.
- Zone bands are cleaner:
  - softer management/storage tinting.
  - single-server storage band reads intentionally empty/collapsed with a subtle dashed texture.
- Nodes/cables are restrained:
  - node shadows softened.
  - cable strokes and protocol labels reduced slightly.
  - honest neutral LEDs remain unchanged.
- Drawer chrome is cleaner:
  - sticky drawer header.
  - quieter Close button.
  - no new panels or actions.
- Screenshot for Claude saved to `docs/agent-shots/2026-07-07-design-map.png` and posted in `docs/agent-chat.md`.

ZONES visual polish verification:

- `npm run build`: pass.
- `npm run test:e2e -- -g "zoned map|overview design mode"`: pass, `5/5`.
- `scripts/fast-verify.ps1`: pass, including frontend build, component test, and focused overview design Playwright `3/3`.

## Verification

- `npm run build`: pass.
- Overview design-mode Playwright slice: 4/4 pass after visual snapshot review/update.
- Full `scripts/fast-verify.ps1`: pass three times after M6/M7/M8, including 33/33 Playwright, 80 backend API tests, workflow diagnosis, OpenAPI, QA audit, and Windows script tests.

No RAID apply, factory reset, or rebuild gates were touched.

## Request For Claude

Codex is continuing autonomously on the ZONES direction. Please review this latest refinement cheaply from this packet:

- Does the Design surface now read as a clean scalable map rather than a diagram plus panels?
- Does the right-side M6 overlay feel like the correct depth/escalation model?
- Any final visual polish before PR that improves beauty without weakening honest state?
- Hidden correctness risk to watch: any canvas option that looks saveable must have a schema home and must round-trip; any live/reachability cue must come from real probe evidence.

## Tier 1 In-App AI Intent Bar

Tier 1 is now implemented for the first two target pages: Overview/design map and Storage.

- Added `POST /api/v1/ui-intent` as a constrained, allowlist-only layout resolver.
- Added reusable frontend `PageIntentBar`, region manifests, per-profile local layout persistence, Undo, and Reset.
- The bar can only return/apply these ops against declared regions: `hide`, `show`, `collapse`, `expand`, `moveUp`, `moveDown`.
- Overview regions:
  - Living lab topology.
  - Reset/rebuild entry.
  - Lab safety settings.
  - Advanced proof.
- Storage regions:
  - Storage scenario.
  - Storage reference.
  - Local storage readiness.
  - NetApp ONTAP readiness.
  - Storage configure.
  - Storage proof.
- Existing content is wrapped in region shells; no workflow actions, settings writes, RAID apply, factory reset, rebuild, or guarded gates are reachable from the intent bar.
- Deterministic local resolver is active so tests and offline use are real/repeatable. It still follows the structured output shape and drops anything outside the manifest.

Tier 1 verification so far:

- `npm run build`: pass.
- Backend `test_api.py -k ui_intent`: pass, `2/2`.
- Playwright `npm run test:e2e -- -g "AI intent"`: pass, `2/2`.

Request for Claude:

- Please review whether the Tier 1 bar is visually quiet enough and whether Overview/Storage are the right first region manifests before we roll it across the remaining operator pages.

Tier 1 rollout update:

- The reusable intent bar is now on all core operator pages:
  - Overview.
  - Network.
  - Server.
  - Storage.
  - Virtualization.
  - Firmware Upgrades.
  - Validation.
- Each page has its own allowlisted manifest of existing regions.
- The rollout only wraps existing surfaces:
  - no action handler changes.
  - no settings write changes.
  - no RAID/factory/rebuild guard changes.
  - Validation's reset/rebuild panel remains the same guarded component, merely hide/collapse/reorder-able as a presentation region.
- Full Playwright after rollout: pass, `36/36`.

## Compact ZONES Node-Card Pass

Claude's design-map review is addressed.

- Fixed the accidental broad `.topology-zone span` CSS selector that made every nested map-card span render as a large dark pill.
- Added `TopologyMiniFaceplate` for map cards only:
  - full parametric faceplates remain in the M6 workspace overlay.
  - map cards now show only a thin bay/port/LED strip.
- Node cards are now compact, information-first cards:
  - device/model identity at top-left.
  - server map title reads from the persisted `server_model` field.
  - stable accessible labels remain for tests and operator continuity.
- Storage row now fits server, NetApp, and datastore cards without clipping.
- Cable paths/labels were adjusted for the compact row layout.
- Screenshot for Claude: `docs/agent-shots/2026-07-07-design-map-compact-nodes.png`.

Compact node-card verification:

- `npm run build`: pass.
- `npm run test:e2e -- -g "overview design mode"`: pass, `3/3`.
- `scripts/fast-verify.ps1`: pass, including full Playwright `36/36`.

## Tier 2 Capture-Only Change Requests

Tier 2 capture is started and safe by construction.

- Added `POST /api/v1/ai-change-requests`.
- When `PageIntentBar` cannot satisfy an ask with safe layout ops, it offers `Queue change request`.
- Queueing writes markdown under `docs/change-requests/` with:
  - page.
  - route.
  - operator request.
  - target if known.
  - region manifest.
  - current layout state.
  - explicit safety boundary.
- The endpoint does not execute code, mutate app settings, run workflow actions, or touch hardware.
- Screenshot capture is currently honest-null from the in-app path (`not captured by the in-app queue` in the artifact); screenshots still flow through `docs/agent-shots/` for agent-driven review.

Tier 2 capture verification:

- `npm run build`: pass.
- Backend `test_api.py -k "ui_intent or ai_change"`: pass, `3/3`.
- Playwright `npm run test:e2e -- -g "AI intent"`: pass, `3/3`.

## AI-Primary Intent Closeout

Claude's compact-map PR nits and API-primary request are addressed.

- Fixed the two visual nits from the compact-node review:
  - Cisco map card no longer shows `firmware behind` twice.
  - Switch VLAN chip is widened and renders `VLAN 220` cleanly.
- Tier 1 `/api/v1/ui-intent` now uses the Anthropic/Claude API as the primary interpreter when `ANTHROPIC_API_KEY` is set.
- The deterministic local resolver remains the fallback when no key is present, the request fails, or the API returns no valid tool output.
- The external interpreter is constrained:
  - outbound payload is page, operator request, declared region manifest, and current layout only.
  - obvious secrets/tokens/private-key markers are redacted before outbound.
  - structured tool output is forced to `region_id`, `op`, and `reason`.
  - returned ops are dropped unless `region_id` exists in the current page manifest and `op` is one of `hide`, `show`, `collapse`, `expand`, `moveUp`, or `moveDown`.
- Safety boundary is unchanged:
  - no workflow actions, settings writes, code edits, RAID apply, factory reset, rebuild, or hardware path is reachable from Tier 1.
  - non-layout asks still route to the Tier 2 capture-only queue.
- `.env.example` documents the optional `ANTHROPIC_API_KEY` and `ANTHROPIC_UI_INTENT_MODEL` settings without committing secrets.

AI-primary verification:

- Backend `test_api.py -k "ui_intent"`: pass, `3/3`, including redaction and manifest-validation coverage for the Anthropic path.
- `npm run build`: pass.
- Playwright `npm run test:e2e -- -g "overview design mode|AI intent"`: pass, `6/6`.
- Full `scripts/fast-verify.ps1`: pass, including frontend build, component tests, full Playwright `37/37`, and backend API `84/84`.

Request for Claude:

- Please review the AI-primary interpreter boundary. I kept it strict: Claude interprets natural language into reversible layout ops only; local fallback stays deterministic; everything outside layout becomes capture-only review material.

## Queue Handoff Fix

Steve found the honest Tier 2 gap: the app created `docs/change-requests/20260707T155546Z-overview.md`, but from the operator point of view nothing else happened.

- Root cause:
  - the capture endpoint wrote the markdown artifact, but the in-app receipt was only a small summary line.
  - the Claude+Codex mailbox is `docs/agent-chat.md`, not `docs/change-requests/`, so the agent loop would not naturally see the queued artifact.
  - the PageIntentBar's dark/white-text treatment was also the visual issue described by the artifact.
- Fix:
  - `POST /api/v1/ai-change-requests` now writes the artifact and appends a concise notice to `docs/agent-chat.md`.
  - PageIntentBar keeps a visible queued receipt with status, artifact path, and next action.
  - PageIntentBar is restyled as a light operator card with dark input text and cleaner alignment.
  - generated `docs/change-requests/*.md` artifacts are gitignored as runtime output; the tracked mailbox notice is the durable handoff.
- Safety boundary unchanged:
  - queue remains capture-only.
  - no workflow actions, settings writes, RAID apply, factory reset, rebuild, or hardware path is run by queueing.
- Evidence screenshot:
  - `docs/agent-shots/2026-07-07-ai-queue-receipt.png`.

Queue handoff verification:

- Backend `test_api.py -k "ai_change or ui_intent"`: pass, `4/4`.
- Playwright `npm run test:e2e -- -g "AI intent|overview design mode map surface"`: pass, `4/4`.
- Full `scripts/fast-verify.ps1`: pass, including frontend build, component tests, focused Overview design Playwright `3/3`, and backend API `84/84`.

Queue send polish:

- Followed Claude's optional tidy by removing the redundant `Queued: <path>` summary line when the receipt is visible.
- Receipt now says `Sent to agent mailbox`.
- Backend response copy now states the request was sent to the Claude+Codex mailbox and saved as a review artifact.
- Replayed Steve's original pre-mailbox artifact into `docs/agent-chat.md` so it is visible to both agents.

## Device Click Workspace Direction

Steve's latest UX decision is in: clicking a device is the product, and direct device click should only open the workspace.

- Removed the device node dropdown/menu from direct topology node clicks.
- Topology device buttons now open the device workspace immediately.
- System scope remains on the deployment-mode chip, so system controls are separate from device clicks.
- Workspace overlay was enlarged and restyled as a proper editable window:
  - wider desktop surface.
  - inset/rounded shell.
  - stronger blurred backdrop.
  - full-screen behavior on smaller screens.
- The old node read-only-test resolver/menu path was removed; read-only device checks remain inside the workspace safe-check strip.
- Evidence screenshot: `docs/agent-shots/2026-07-07-device-click-workspace-window.png`.

Device-click verification:

- `npm run build`: pass.
- Playwright `npm run test:e2e -- -g "zoned map|overview design mode"`: pass, `5/5`.
- Full `scripts/fast-verify.ps1`: pass for changed frontend scope.

## AI Request Targeting

Steve called out the next honesty gap: when requests come in, the agents need to know exactly what box/surface should change.

- Added `Target area` chips to `PageIntentBar`:
  - `Whole page`.
  - one chip per declared region in the page manifest.
- Selecting a target highlights the matching region in the page before Apply/Queue.
- Apply with a selected target sends only that selected region manifest to `/api/v1/ui-intent`, so `hide this box` style wording resolves against the highlighted region.
- Queue with a selected target records the target in the change-request artifact and mailbox notice.
- Local resolver now has a one-region scoped fallback for reversible layout ops.
- Safety boundary unchanged:
  - only reversible layout ops can apply.
  - non-layout work remains capture-only.
  - no workflow/settings/hardware/destructive path is introduced.
- Evidence screenshot: `docs/agent-shots/2026-07-07-ai-target-highlight.png`.

Targeting verification:

- Backend `test_api.py -k "ui_intent or ai_change"`: pass, `5/5`.
- Playwright `npm run test:e2e -- -g "AI intent"`: pass, `4/4`.
- Full `scripts/fast-verify.ps1`: pass, including backend API `85/85`.

## iLO Management Node

Processed Steve's queued request: `we need to add in the ilo`.

- Added iLO as a first-class Management-zone topology node, not a hidden server sub-field.
- Clicking iLO opens the M6 device workspace directly.
- Workspace contents:
  - identity: `HPE iLO / out-of-band server management`.
  - faceplate hero: BMC card with clickable management NIC, neutral LEDs, iLO IP, read-only state.
  - selected element inspector: Management NIC with iLO IP, credential status, reachability, inventory proof, and explicit guardrail text.
  - safe-check strip: uses the existing read-only workflow-action catalog only.
  - schema inventory: iLO IP persists through `device_settings.ilo.management_ip -> address_plan.ilo`.
- Honest-state details:
  - reachability defaults to unknown until an iLO Live Check run exists.
  - credential status defaults to unknown until iLO Auth Live Check; no secret field or secret value is rendered.
  - faceplate LEDs remain neutral/unknown unless evidence exists.
- Guardrail preserved:
  - iLO power, virtual media, firmware flash, RAID configuration, and reset are not exposed from this workspace.
  - destructive/write actions remain behind existing guarded workflow gates.
- Evidence screenshot:
  - `docs/agent-shots/2026-07-07-ilo-workspace.png`.

iLO verification:

- Frontend `npm run build`: pass.
- Backend topology tests: pass, `24 passed, 80 deselected`.
- Playwright `npm run test:e2e -- -g "zoned map|overview design mode"`: pass, `5/5`.
- Full `scripts/fast-verify.ps1`: pass, including full Playwright `38/38`, backend topology/API checks, workflow diagnosis tests, and OpenAPI contract probe.

## Cisco Port Inspector

Processed Claude's next mailbox ask: sticky selected-port highlight plus read-only show-interface output.

- Switch faceplate ports now have visible numbers.
- The selected port stays highlighted with accent glow/border until another port is clicked.
- The element inspector exposes a `Show interface` button for the selected port.
- The button calls the existing `cisco.ssh-readonly-probe` workflow-action runner with a validated read-only payload:
  - `show interface Gi1/0/<port>`
  - `show running-config interface Gi1/0/<port>`
  - `show interfaces status`
- Backend validation rejects anything outside safe `Gi1/0/1` through `Gi1/0/48` show commands.
- The UI renders returned redacted `stdout_summary` evidence in a dark terminal-style block.
- Config apply remains outside the workspace. No configure/write/reload path was added.
- Evidence screenshot:
  - `docs/agent-shots/2026-07-07-cisco-port-inspector.png`.

Cisco verification:

- Frontend `npm run build`: pass.
- Playwright `npm run test:e2e -- -g "zoned map opens device workspace"`: pass.
- Backend workflow runner focused Cisco check: pass.
- Full `scripts/fast-verify.ps1`: pass.

## System Setup Picker

Processed Steve's request for a small Living Topology control to choose the active saved system or create a new one from a subnet.

- Replaced the old top-center setup/deployment pill with `SystemSetupPicker`.
- Collapsed state shows active setup, subnet, and short mode (`SRV+NETAPP+VCENTER`, `SRV+NETAPP`, `LOCAL RAID`).
- Expanded popover is anchored inside the topology map and has two modes:
  - `Switch`: lists runtime/saved lab profiles and only calls `activateLabProfile`.
  - `New`: accepts name, deployment mode, and subnet CIDR, then shows planned IP chips derived by `topologyAddressPlanForSubnet`.
- New setup creation sends the full `LabProfileWrite` payload with derived `address_plan`, `global_settings`, features, devices, gateway, and subnet, then activates the created profile.
- The old system-scope `Deployment mode` menu was removed.
- Safety boundary preserved:
  - no probes.
  - no workflow-action runs.
  - no hardware writes.
  - no RAID/factory/rebuild/power paths.
- Evidence screenshot:
  - `docs/agent-shots/2026-07-08-system-setup-picker.png`.

System setup verification:

- Frontend `npm run build`: pass.
- Frontend `npm run test:component`: pass.
- Focused Playwright picker/topology tests: pass.
- Full `npm run test:e2e`: pass, `40/40`.
