# UX Simplification Audit

## Top 10 Clutter Problems

1. Provider tabs are the primary navigation, but the operator workflow is stage-based.
2. The real-lab banner dominates the top of the page before the user sees what to do.
3. Lab-wide reports appear before the active build journey.
4. Provider cards contain summary, detail, actions, protected actions, and diagnostics in one long panel.
5. iLO, RAID, and ESXi are nested under one provider instead of shown as distinct stages.
6. Cisco shows readiness, wizard plan, bootstrap requirements, command previews, and disabled actions together.
7. Build Verification shows certification, lab profile, credential, MTU, protocol, failure, and artifact data together.
8. Protected/disabled actions are visually prominent even when they are expected safety gates.
9. Repeated provider mode and apply-disabled facts consume space across sections.
10. Raw paths and command snippets read like tasks even when they are evidence only.

## Top 10 Confusing Labels

1. `Provider Status`
2. `local-lab-readwrite`
3. `blocked_by_prior_stage`
4. `provider-lab-build-verification`
5. `stale_config`
6. `operator_action_required`
7. `GET-Only Endpoint Detection`
8. `Cisco Setup Readiness`
9. `HPE Storage / RAID`
10. `NETAPP_CONFIGURED`

## Top 10 Places Showing Too Much Detail

1. iLO configuration flags on the default screen.
2. iLO capability and provider mode facts.
3. Cisco console candidates and read timing.
4. Cisco bootstrap command previews.
5. Cisco disabled dangerous actions.
6. RAID reset command text.
7. RAID current physical/logical drive tables.
8. ESXi virtual media and boot-control internals.
9. Build Verification credential compatibility checks.
10. Build Verification report paths and stale artifact evidence.

## Top 10 Missing Next Action Messages

1. Lab Profile needs a simple confirm/review action.
2. Cisco needs one top blocker and one recommended action.
3. HPE Server needs a server validation action separate from RAID.
4. RAID needs a clear "save/validate desired layout" action.
5. ESXi needs a clear install-readiness action.
6. NetApp needs "configure planned targets" when not configured.
7. Build Verification needs "run after earlier stages pass."
8. The top of the page needs one overall next action.
9. Blocked-by-prior-stage sections need to say which stage they wait on.
10. Advanced diagnostics need to say they are optional evidence.

## Collapse By Default

- Lab-wide report details.
- Provider evidence and raw redacted probe payloads.
- Protected and disabled action lists.
- Cisco console candidates and command previews.
- iLO setup intent form.
- RAID drive/controller tables and reset commands.
- ESXi virtual media internals.
- NetApp planned/current target tables and artifact placeholders.
- Build Verification credential, MTU, protocol, and artifact details.

## Combine

- Provider tabs should become a single guided workflow lane.
- iLO provider summary should split visually into HPE Server, RAID / Storage, and ESXi Install stage cards.
- Lab-wide reports and Build Verification should become a final Build Verification stage plus advanced diagnostics.
- Provider mode and safety posture should become one short overview line.

## Simplify Badges

- `ready` -> `Ready`
- `ok` -> `Ready`
- `blocked` -> `Needs attention`
- `failed` -> `Needs attention`
- `missing-config` -> `Not configured yet`
- `planned-target` -> `Planned`
- `awaiting-bootstrap` -> `Waiting`
- `blocked_by_prior_stage` -> `Waiting on earlier step`

## Advanced Details Data

- Raw reports and artifact paths.
- JSON payload fields.
- Command text and confirmation phrases.
- Provider modes and env flag detail.
- Endpoint paths and status codes.
- Console adapter tables.
- Drive/controller tables.
- Credential compatibility internals.
- MTU and protocol check internals.
- Full disabled-action inventories.
