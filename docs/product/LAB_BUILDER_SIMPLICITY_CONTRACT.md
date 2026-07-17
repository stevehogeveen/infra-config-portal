# Lab Builder Simplicity Contract

Normal operator mode is allowed to be calm even when the dependency engine is complex. Every operator-facing change must keep the first screen understandable without reading proof logs, dependency graphs, provider payloads, or implementation vocabulary.

## Four-Question Information Budget

The default operator screen may answer only these four questions:

1. Which kit am I working on?
2. What state is the kit in?
3. What needs my attention?
4. What is the next safe action?

Anything else belongs in Details or Advanced.

## One Primary Action

The operator screen gets one primary action. Secondary actions are links, disclosure controls, or details-only controls. If two buttons look equally important, one must be demoted or removed.

## Tiers

- Operator: selected kit, plain-language state, compact device summary, actionable blockers, one primary action, one Details entry.
- Details: topology map, device workspaces, editable setup parameters, non-destructive read-only checks, supporting context.
- Advanced: dependency graph, provider states, raw logs, verification evidence, API payloads, audit proof, manual overrides.

Operator components must not directly import raw provider or diagnostic components.

## One Fact, One Owner, One Display Location

Every fact has one canonical owner and one default display location. A readiness result must not appear as a header badge, card, table row, drawer summary, and map label at the same time. If a fact needs to appear in another tier, it must be summarized there and point back to the canonical owner.

## Operator Vocabulary

Use words an operator would say in the room: kit, device, switch, server, storage, ready, blocked, needs attention, next action, proof.

Avoid normal-mode terms such as provider, runtime, payload, dependency graph, artifact, raw result, workflow slug, or environment mode. Those terms can exist in Advanced proof only.

## Exceptions Over Inventory

Summarize healthy devices. Expand only items requiring action or review. Do not create grids of green success cards.

## Replace, Don't Add

When simplifying a surface, replace the old surface. Do not add a cleaner panel while retaining the old equivalent panel below it.

## Five-Second Test

A new operator should be able to look at the default screen for five seconds and say:

- which kit is selected
- whether the lab is ready, blocked, or needs attention
- what device, if any, needs action
- what single action to take next

If they need to open Details to answer any of those, the operator surface failed.

## Amendment 1: Navigation Spine

Recorded deliberately (CXO), superseding the earlier absolute "no new top-level navigation."
The product grew real Setup and Run phases, so a stable navigation spine now aids
discoverability instead of causing sprawl. See `LAB_BUILDER_IA_ALIGNMENT_BRIEF.md`.

Permitted navigation is exactly one fixed three-phase spine:

- **Overview** — the Operator Home dashboard (status, map, one next action).
- **Setup** — the setup modules (iLO, Storage, ESXi, Windows, Cisco, NetApp, OVF, Firmware,
  Global). Details tier.
- **Run** — Run Center (the build journey) and Reports.

Rules that still bind:

- No navigation beyond this spine. No ad-hoc tabs. No per-device surface on Operator Home.
- Operator Home still obeys the Four-Question Information Budget and shows one primary action.
- The build step list lives in Run Center, never on the Overview dashboard.
- Every other section of this contract (tiers, one fact/one owner, operator vocabulary,
  exceptions over inventory, replace-don't-add, five-second test) is unchanged.
