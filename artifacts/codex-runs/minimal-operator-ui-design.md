# Minimal Operator UI Design

Date: 2026-06-09

Scope: frontend presentation and summary shaping only. Backend capabilities remain available.

## Standard Compact Summary Shape

Every default stage summary should be shape-compatible with:

```ts
type MinimalStageSummary = {
  label: string;
  status: string;
  one_line_summary: string;
  next_action: string;
  primary_button_label: string;
  primary_button_enabled: boolean;
  secondary_action_label?: string;
  blocker_count: number;
  proof_count: number;
  last_checked: string | null;
  advanced_available: boolean;
};
```

## Default Visible Content

- Stage name.
- Status pill.
- One sentence describing current state.
- One next action.
- One primary action.
- One blocker if present.
- A small "proof available" count or collapsed Evidence affordance.

## Hidden By Default

- Report paths.
- JSON.
- Command text.
- Long blocker lists.
- Raw evidence.
- Registry metadata.
- Run trace details.
- Safety gate internals.
- Source/freshness internals unless stale/current materially changes what the user should do.

## Display Modes

### Simple Mode / Operator Mode

Default.

- Minimal content.
- List/detail layouts.
- Evidence collapsed.
- Only next action and status visible.
- One primary action visible per selected row.
- Human labels instead of registry IDs or backend state constants.

### Advanced Mode

Optional, stored as local UI state.

- Action catalog details.
- Commands.
- Report links.
- Evidence artifacts.
- Run traces.
- Gates and confirmations.
- Source/freshness details.
- Raw redacted payloads where already supported.

## Lab Setup Contract

Default Lab Setup is a compact list:

- Lab Profile
- Firmware
- Cisco
- HPE / iLO
- RAID / Storage
- ESXi
- NetApp
- Build Verification

Each row shows:

- Status.
- Summary.
- Next action.
- Primary button or disabled reason.

Selecting a row opens a detail panel with:

- Must-have current state.
- Must-have desired state.
- Next action.
- Primary action.
- Advanced details collapsed.

No report list appears on this page in Simple mode.

## NetApp Contract

Default NetApp view shows:

- Console: detected / not detected.
- ONTAP state: setup wizard / configured / unknown.
- Management: configured / not configured.
- NFS datastore: ready / not created / blocked.
- Upgrade: ready / disabled / blocked.
- Next action.

Required summaries:

- Console detected at 115200 -> "Console detected".
- `cluster_setup_wizard` -> "Setup wizard detected".
- Missing setup intent fields -> "Setup details missing".
- Upgrade disabled -> "Upgrade disabled until ONTAP setup is complete."

Advanced includes:

- Report paths.
- Local media inventory details.
- Make target names.
- Registry action IDs.
- Exact confirmation flag names.
- Long planned API call lists.
- Raw ONTAP upgrade conditions.

## Firmware / Upgrade Contract

Default view:

- iLO: passed/current version.
- Cisco: passed/unknown/needs check.
- ONTAP: not configured yet/current version/upgrade available.
- Packages: available/missing.
- Next action.

Advanced includes:

- Baseline manifest details.
- Waiver internals.
- Package path lists.
- Raw version comparisons.
- Upgrade command internals.

## Reports Contract

Default Reports page:

- Issue summary counts.
- Top 3 fixes.
- Compact issue rows for the selected filter.
- Grouped evidence collapsed.

Do not show every report path as a separate "Needs attention" row.

## Control Center Contract

Simple table columns:

- Action.
- Stage.
- Type.
- Status.
- Run / Copy.

Advanced/details include:

- Full command.
- Gates.
- Report paths.
- Run trace internals.
- Registry IDs.
- Required confirmations.

## Safety Contract

- No real hardware workflows run from this UI pass.
- Mock/test state is not real lab state.
- Historical artifacts are proof, not current blockers unless a fresh check proves current state.
- Secret values remain absent; credential state is configured/missing/redacted only.
