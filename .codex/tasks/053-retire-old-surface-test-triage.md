# 053 - Test triage after retiring the old topology map

## Goal

The old pre-rack surface has been deleted from `app/frontend/src/operatorPages.tsx`:
`OperatorOverviewPage`, `OverviewLabMap`, `MapDeviceEditor`, `GenericDevicePanel`
and the dead `LabTopologyMap` (~1000 lines). `/overview` and its feeder routes
(`/control-center`, `/settings`, `/providers`) now redirect to `/simple`, the rack
workspace, which is the only home. Kit create/activate/continue now land on
`/simple` instead of the map.

`app/frontend/tests/safe-action-runner.spec.ts` has already been pruned from 132
to 96 tests (36 tests that only described the deleted map/home dashboard were
removed) and the survivors were repointed from `/overview` to `/simple`. About
24 still fail because they assert against surfaces that moved or no longer exist.

Your job: get `npm run test:e2e` fully green **without weakening real coverage**.

## Rules for each failing test

Decide per test, in this order:

1. **The behaviour still exists somewhere** → repoint the test at the surface that
   now hosts it and fix selectors. Examples already done that you should copy:
   - Build-runner tests: replaced the old `operator-home-primary-action` hop with
     `await page.goto("/run-center")`.
   - `local RAID draft starts from the live discovered layout instead of the canned
     template` (now passing): uses `labProfileScenario = "single"`, `goto("/storage")`,
     clicks `Plan ports and bays`, then asserts on
     `section[aria-label='Local RAID planner']`. The storage workspace loads discovery
     itself, so the old "No iLO drive inventory yet" + "Read storage from iLO"
     precondition from the deleted map drawer must be dropped.
2. **The behaviour is genuinely gone with the deleted surface** → delete the test.
   Do not keep a test that asserts a deleted component renders.
3. **Never** weaken an assertion just to make it pass — no `.catch()`, no
   `test.skip`, no deleting the meaningful assertions while keeping a hollow test,
   no loosening a count/matcher that was protecting a real guarantee.

## Coverage that MUST survive (repoint, never delete)

These protect real safety behaviour that still exists:
- Per-device iLO isolation (two iLO devices keep separate access settings).
- iLO proof binding: proof only counts for the exact current target; editing the
  target invalidates it; access-settings failure falls back to the initial address
  and never the planned one.
- Local RAID live-seed honesty: the seed is refused when volume members cannot be
  paired to bays; DL380 cross-view members pair through hardware fingerprints;
  cross-view vSAN readiness renders by paired physical bay.
- Guarded/destructive actions stay behind confirmations and off default surfaces.
- Read-only checks stay read-only (`expect(mutations).toEqual([])` style assertions).

## Also required

Replace the now-wrong guard in the rack test that asserts removal does not exist
(`await expect(page.getByText("Remove from lab")).toHaveCount(0);`). The rack now
has a real "Remove from rack" button with a confirmation dialog
(`.rack-remove-overlay`, `.rack-remove-panel`, buttons "Keep it" and "Remove from
rack"). Add a positive test proving: the button exists, cancelling makes no request,
confirming issues exactly one `DELETE /api/v1/device-inventory/{id}`, and the device
disappears from the rack.

## Explicitly do NOT

- Do not restore, recreate, or re-add the deleted map/overview components.
- Do not touch `app/frontend/src/simplePages.tsx` behaviour or the backend.
- Do not touch `app/frontend/app/` (pre-existing untracked scratch).
- Do not commit.

## Verify

`npx tsc --noEmit`, `npm run build`, and the full `npm run test:e2e` all clean.
Report the final pass count and list every test you deleted with a one-line reason.
