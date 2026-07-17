# Lab Builder Derived Fact Audit

Date: 2026-07-17
Scope: `app/frontend/src`
Mode: report-only; no fixes included

This audit applies the **One Fact, One Computation** rule from the Simplicity
Contract. The canonical Operator Home owner is
`app/frontend/src/operatorHomeModel.ts`; views should consume its fields rather
than reconstructing counts or display state.

## Confirmed Findings

### High: empty-device total violates the progress invariant

- Owner: `app/frontend/src/operatorHomeModel.ts:83-86`
- Canonical computation: `readyCount`, `blockedCount`, and `notCheckedCount`
  are derived from `deviceSummary`.
- Divergent computation: `totalCount` is `Math.max(deviceSummary.length, 1)`.
- Why it matters: with zero devices, the three parts sum to `0` while `Total`
  reports `1`; the model can say `0 of 1 devices ready` without any device.
- Can disagree now: yes, on an empty or not-yet-populated model.
- Recommended fix for CXO triage: use the actual summary length as `Total` and
  keep zero-denominator handling in the meter formatter/view.

### High: Operator Home view recomputes `NotChecked`

- Owner: `app/frontend/src/operatorHomeModel.ts:83-86,111-116`
- View: `app/frontend/src/components/operator/OperatorHomeView.tsx:20-25`
- Canonical computation: the model provides `Progress.NotChecked`.
- Divergent computation: the view derives `unchecked` as
  `total - ready - blocked`, after clamping the other values.
- Can disagree now: yes, if the model is invalid, if a future status category
  is added, or if clamping changes the arithmetic.
- Recommended fix for CXO triage: render `model.Progress.NotChecked` directly;
  keep only presentational percentage calculation in the view.

### Medium: Operator Home view recomputes display tone

- Owner: `app/frontend/src/operatorHomeModel.ts:87,101`
- View: `app/frontend/src/components/operator/OperatorHomeView.tsx:25`
- Canonical computation: `model.DisplayState` is the model-owned display state.
- Divergent computation: the view maps `blocked > 0` to `blocked`, otherwise
  `attention`, with a special case for `ready`.
- Can disagree now: yes, for a future `DisplayState` value or when attention
  items and blocked devices do not have the same meaning.
- Recommended fix for CXO triage: map the model's display state directly to a
  CSS tone without consulting progress counts.

### Medium: iSCSI reachability has an API-count/fallback-count fork

- Location: `app/frontend/src/operatorPages.tsx:2340-2345`
- Preferred source: `option.reachable_lif_count` from the backend response.
- Fallback source: a frontend filter over `option.checks`.
- Can disagree now: yes, if both fields are present but stale or computed with
  different inclusion rules. This is page-scoped diagnostic data, not the
  Operator Home readiness model, but it should be resolved at the API/model
  boundary before becoming operator-facing summary data.

## Reviewed And Not Classified As Duplicates

- `App.tsx` stage-action counts summarize run traces; they are not the
  Operator Home device readiness counts.
- Firmware row counts summarize firmware inventory/compliance rows; they are a
  different domain fact and should get their own canonical firmware model when
  the firmware slice begins.
- Storage and iSCSI blocker arrays represent different provider scopes and are
  intentionally combined with de-duplication before display.

## Required Follow-Up Before The Next Slice

1. CXO review of the four findings above.
2. Fix only the approved model/view findings in a focused commit.
3. Add an empty-summary regression and keep the existing readiness invariant.
4. For firmware, define the row status/count owner before adding any new table,
   map, rail, or summary presentation.
