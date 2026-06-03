# 046 - Firmware Upgrade Decision Engine

## Goal

Add a firmware/software upgrade decision engine framework.

The app must compare:

- what is currently installed/discovered
- what upgrade media/catalog candidates are available
- what upgrade path/rules are known
- what blockers or warnings apply

This task should focus first on iLO firmware upgrade readiness, but the model should be reusable later for ESXi, Cisco, NetApp, firmware bundles, OVFs, and other upgrade flows.

## Product Rule

Do not simply show that firmware media exists.

Show:

- current discovered version
- discovered platform/generation
- available candidate versions
- confidence of match
- known upgrade path if available
- blockers
- removable warnings
- next safe action

## Safety

This is planning only.

Do not:

- upload firmware
- flash firmware
- reboot/reset
- mount media
- deploy OVF
- run upgrades
- change iLO settings
- change ESXi
- change Cisco
- change NetApp
- call destructive provider actions

Do not commit firmware/media files.

Do not print or commit secrets.

## Concepts

Add a reusable upgrade decision model.

Suggested concepts:

- `UpgradeSubject`
  - provider_type
  - product
  - generation
  - model
  - serial
  - current_version
  - discovery_confidence

- `UpgradeCandidate`
  - id
  - category
  - product_hint
  - generation_hint
  - version
  - source
  - redacted_label
  - match_confidence
  - warnings

- `UpgradeRule`
  - product
  - generation
  - from_constraint
  - to_constraint
  - requires_intermediate
  - blocked_reason
  - warning
  - source
  - confidence

- `UpgradeDecision`
  - status:
    - current
    - upgrade_available
    - upgrade_recommended
    - upgrade_required
    - blocked_unknown_path
    - blocked_incompatible
    - manual_review_required
    - no_candidate_found
    - discovery_incomplete
  - current_version
  - recommended_target
  - required_intermediate_versions
  - candidate_chain
  - blockers
  - warnings
  - removable_warnings
  - next_safe_action
  - apply_enabled false

## Blockers vs Removable Warnings

Blockers stop the plan/apply path.

Examples:
- current firmware version unknown
- device generation unknown
- no candidate found
- candidate does not match device generation
- upgrade requires intermediate version but media is missing it
- upgrade path is unknown
- endpoint cannot confirm target identity

Removable warnings do not automatically stop planning but require attention.

Examples:
- candidate matched by filename only
- multiple candidates found
- upgrade may require iLO reset
- local catalog lacks release notes
- current version older but still supported
- version parsing was heuristic

## iLO Upgrade Decision

Integrate with the iLO setup/upgrade path UI.

Use available data:
- current iLO firmware from discovery if known
- iLO generation if known
- server model if known
- media inventory firmware candidates

If exact HPE upgrade rules are not known, do not invent them.

Instead:
- mark upgrade path as `manual_review_required` or `blocked_unknown_path`
- show candidate media
- explain that rules/catalog must be added
- provide next safe action

Add a small local sample rules/catalog structure if useful, but make clear it is sample/framework only.

Do not claim real HPE compatibility unless the rule is encoded with a source.

## Media Matching

Improve firmware candidate matching.

Match by:
- extension/category
- filename hints
- parsed version if possible
- product/generation hints like ilo4, ilo5, ilo6, gen10, gen11, spp, hpe

Return confidence:
- exact
- likely
- weak
- unknown

Weak/unknown matches should create warnings or blockers.

## Backend Work

Add service/model code for upgrade decisions.

Add or improve API response for iLO upgrade readiness so it includes:
- subject
- candidates
- decision
- blockers
- warnings
- removable_warnings
- upgrade_chain
- apply_enabled false

If there is already an iLO plan/readiness endpoint, extend it.

If not, add one cleanly.

## Frontend Work

Improve iLO upgrade card.

Show:
- current firmware
- detected generation/model
- available firmware candidates
- recommended target if known
- required intermediate versions if known
- blockers
- removable warnings
- next safe action
- apply/flash disabled
- explicit note: plan only, no firmware actions run

## Tests

Normal tests must not require real hardware or real media.

Add tests for:
- no current version gives discovery_incomplete blocker
- no candidate gives no_candidate_found
- weak filename match creates warning/manual review
- candidate incompatible with generation creates blocked_incompatible
- missing intermediate creates blocked_unknown_path or equivalent blocker
- valid simple upgrade path returns upgrade_available/recommended
- current version equal newest returns current
- apply_enabled is always false
- iLO upgrade readiness response includes decision

## Documentation

Update docs with:
- upgrade decision model
- blockers vs removable warnings
- manual review behavior
- media matching confidence
- no firmware apply yet
- future real catalog/rules requirement

## Quality Gates

Run:

- PROVIDER_MODE=mock make smoke
- PROVIDER_MODE=mock make test
- PROVIDER_MODE=mock make lint
- PROVIDER_MODE=local-readonly make provider-smoke || true
- git diff --check

## Acceptance Criteria

- Upgrade readiness is a decision, not just a media list.
- iLO upgrade card shows current vs available vs decision.
- Unknown upgrade paths are blocked or marked manual review.
- Removable warnings are separated from blockers.
- Apply/flash remains disabled.
- Tests pass in mock mode.
