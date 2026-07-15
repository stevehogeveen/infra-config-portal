# Lab Builder Operator Surface Inventory

Date: 2026-07-15

## Duplicate Readiness Displays

- Overview header previously carried readiness copy and a run button.
- Living topology footer also carried a next-safe-action line.
- Advanced proof repeated current-view rows, inventory rows, validation rows, and lab safety state.
- Firmware had already been decluttered into a map-first surface; this slice keeps that pattern.

Resolution: Overview now has one canonical Operator Home readiness result. The topology, inventory, validation proof, and safety audit are demoted behind the single View Details entry point.

## Duplicate Blocker Messages

- Validation top blocker, topology footer next action, provider/access rows, and advanced proof could repeat similar blocker copy.
- Some old copy pointed operators to removed pages such as Storage.

Resolution: Operator Home renders actionable attention items once in plain language. Details retain raw proof only after disclosure.

## Repeated Device State Summaries

- Device state appeared in topology nodes, access rows, inventory rows, workspace rows, and validation rows.

Resolution: Operator Home summarizes healthy devices as a count and expands only devices needing attention. Full device state remains in the topology/workspace tier.

## Provider Or Environment Terminology Shown To Operators

- Advanced proof used runtime mode, provider status, validation rows, and build verification terms.
- Topology status included technical runtime wording.

Resolution: the default Operator Home model uses kit, device, lab, state, and next action vocabulary. Provider and proof vocabulary stays in Details/Advanced.

## Duplicate Console Controls

- Console discovery existed in device workspaces and was also referenced from readiness/access summaries.

Resolution: console-specific controls remain in the relevant device workspace. Operator Home shows only the device that needs attention and the plain next action.

## Old Entry Points Superseded By Operator Home

- Overview layout AI bar.
- Overview topology as the default home surface.
- Overview reset/rebuild link.
- Overview advanced proof drawer on the normal path.

Resolution: these are removed from the default operator path. The topology and proof are reachable only through View Details; reset/rebuild remains on Validation where its guarded workflow belongs.

## Recommended Next Task

Add a follow-up Details-tier cleanup that trims topology footer counts and remaining technical wording without changing the Operator Home contract.
