# Minimal Operator Label Map

Date: 2026-06-09

Use these labels on main operator surfaces. Raw values may remain in Advanced details.

| Technical label | Human label |
| --- | --- |
| `cluster_setup_wizard` | Setup wizard detected |
| `not_configured_yet` | Not configured yet |
| `blocked_by_prior_stage` | Waiting on earlier step |
| `local-lab-readwrite` | Real Lab Mode |
| `local-readonly` | Read-only Lab Mode |
| `historical_artifact` | Previous evidence |
| `live_probe` | Live check |
| `live_cached` | Recent live check |
| `not_checked` | Not checked |
| `test_fixture` | Test fixture |
| `provider-lab-netapp-ontap-upgrade-validate` | Validate ONTAP upgrade |
| `provider-lab-netapp-ontap-upgrade-plan` | Plan ONTAP upgrade |
| `provider-lab-netapp-ontap-upgrade-inventory` | Check ONTAP upgrade package |
| `provider-lab-netapp-setup-preview` | Preview NetApp setup |
| `provider-lab-netapp-setup-apply` | Apply NetApp setup |
| `NETAPP_SETUP_APPLY missing` | Setup apply not enabled |
| `NETAPP_CONFIGURED=false` | NetApp is not verified yet |
| `NETAPP_CONFIGURED=true` | NetApp previously marked configured |
| `read_only` | Read only |
| `report_only` | Report only |
| `guarded_write` | Guarded write |
| `operator_action_required` | Needs action |
| `stale_config` | Old config needs review |
| `hard_fail` | Blocked |
| `missing-config` | Not configured yet |
| `missing-console` | Console not found |
| `planned-target` | Planned |
| `setup_intent_missing` | Setup details missing |
| `upgrade_disabled` | Upgrade disabled |
| `apply_enabled=false` | Apply disabled |
| `api_access_present` | Management access configured |
| `source_type` | Source |
| `freshness` | Last checked state |

## Main-Surface Copy Rules

- Do not show registry IDs unless Advanced mode is active.
- Do not show make target names unless Advanced mode is active.
- Do not show exact confirmation flag names unless Advanced mode is active.
- Prefer "Setup details missing" over listing every missing field on the main NetApp surface.
- Prefer "Upgrade disabled until ONTAP setup is complete" over raw upgrade readiness conditions.
