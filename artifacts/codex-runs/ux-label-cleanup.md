# UX Label Cleanup Map

## Applied In UI

| Backend / Old Label | Operator Label |
| --- | --- |
| `provider-lab-build-verification` | Run Build Verification |
| `blocked_by_prior_stage` | Waiting on earlier step |
| `stale_config` | Old lab IP detected |
| `operator_action_required` | Needs your action |
| `local-lab-readwrite` | Real Lab Mode |
| `local-readonly` | Read-only Lab Mode |
| `GET-Only Endpoint Detection` | Read-only endpoint check |
| `GET-only` | read-only |
| `Redfish PATCH accepted` | iLO accepted the storage change |
| `missing-config` | Not configured yet |
| `planned-target` | Planned |
| `awaiting-bootstrap` | Waiting |
| `blocked` | Needs attention |
| `failed` | Needs attention |
| `ok` | Ready |
| `ready` | Ready |

## Product Copy Direction

- Use "Needs attention" for actionable blockers.
- Use "Waiting on earlier step" when a later stage cannot proceed yet.
- Use "Not configured yet" for optional or not-yet-entered provider setup.
- Use "Advanced diagnostics" for raw payloads, report paths, command text, and provider evidence.
- Use "Next action" consistently for the one recommended step in each major card.
