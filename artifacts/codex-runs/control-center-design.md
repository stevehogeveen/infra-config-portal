# Control Center Design

Generated: 2026-06-08

Scope: `/home/administrator/infra-config-portal`

## Product Model

Keep the simplified Lab Builder / Guided View as the default operator path.

Add a top-level Control Center for power users:

- Guided View: simple next-action workflow.
- Control Center: full device/profile/action control.
- Upgrade Center: firmware/software visibility and guarded upgrade planning.
- Action Catalog: every known action visible in one place.
- Lab Profile Editor handoff: profile values and copyable non-secret env updates visible without hunting through files.

The Control Center must be safe by default. It can expose copyable commands and plan endpoints before direct run execution exists. It must not trigger firmware updates, destructive writes, provider writes, power actions, serial writes, or live infrastructure changes in this pass.

## Route And Navigation

Add a top-level route:

- `/control-center`

Add a sidebar item:

- Control Center

Keep these existing routes:

- `/run-center`
- `/providers`
- `/lab-profiles`

## Backend Action Catalog

Add:

- `GET /api/v1/control/actions`
- `POST /api/v1/control/actions/{action_id}/plan`
- `POST /api/v1/control/actions/{action_id}/run`

Direct `run` should be a safe placeholder in this pass. It returns the action, blocker, and suggested command/API endpoint instead of executing real infrastructure actions.

Each action exposes:

- action id
- label
- device/stage
- description
- classification: read-only, write, destructive, or upgrade
- required inputs
- required flags
- required confirmations
- current availability
- blocker if unavailable
- last run status/report
- suggested command or API endpoint

## Control Center Sections

Every section uses the same surface:

- Current state
- Desired state
- Diff/plan
- Primary actions
- Destructive/upgrade actions clearly marked
- Last result
- Report link
- Advanced diagnostics collapsed

### 1. Lab Profile

Current state:

- Active profile name/source
- subnet
- iLO IP
- server embedded NIC IP
- ESXi IP
- Cisco IP
- Ansible/control host IP
- NetApp SP, cluster, node, SVM, and data LIF IPs
- VLAN IDs
- MTU
- DNS/gateway/NTP
- configured flags: `CISCO_MGMT_CONFIGURED`, `ESXI_CONFIGURED`, `NETAPP_CONFIGURED`

Desired state:

- Known lab profile:
  - subnet: `192.168.1.0/24`
  - iLO: `192.168.1.201`
  - server NIC: `192.168.1.202`
  - ESXi: `192.168.1.203`
  - Cisco: `192.168.1.204`
  - Ansible/control host: `192.168.1.205`

Controls:

- Open Lab Profiles editor.
- Copy non-secret env update command.
- Show stale/invalid values.

### 2. Cisco Control

Current state:

- Cisco console status
- selected/effective console path
- management IP
- management configured flag
- prompt classification
- SSH/SCP readiness
- firmware inventory status

Desired state:

- management IP `192.168.1.204`
- console-first bootstrap
- SSH/SCP validation after management is configured
- save config only after guarded apply path

Controls:

- Discover console
- Reclaim console
- Reclaim serial port
- Privilege check
- Firmware inventory
- Apply bootstrap
- Validate SSH/SCP
- Save config
- Reload if needed

### 3. HPE / iLO Control

Current state:

- iLO configured flags
- reachability/auth/inventory status
- model/serial if discovered
- iLO firmware
- virtual media support
- boot control support

Desired state:

- iLO at `192.168.1.201`
- authenticated inventory available before apply paths
- firmware inventory visible
- virtual media/boot controls gated

Controls:

- Reachability
- Auth
- Inventory
- Virtual media insert
- One-time boot
- Reset server
- Firmware inventory

### 4. RAID / Storage Control

Current state:

- controller inventory
- physical drive inventory
- logical drive inventory
- pending reset state
- last validation

Desired state:

- saved HPE RAID intent
- planned OS/data layout
- explicit wipe/destructive gates before apply

Controls:

- Discovery
- Plan
- Apply
- Pending check
- Reset/commit
- Validate

### 5. ESXi Control

Current state:

- ESXi configured flag
- target IP `192.168.1.203`
- ISO/media readiness
- virtual media workflow state
- one-time boot workflow state
- management validation state
- SSH/API probe state

Desired state:

- ESXi installed/configured at `192.168.1.203`
- management network ready
- SSH/API checks available after `ESXI_CONFIGURED=true`

Controls:

- Readiness
- ISO/media check
- Kickstart generation
- Rebuild/install
- Management validation
- SSH/API check

### 6. NetApp Control

Current state:

- `NETAPP_CONFIGURED`
- planned SP and management IPs
- current discovered targets
- console readiness
- REST/SSH readiness
- NFS/vCenter readiness
- setup and upgrade readiness split

Desired state:

- setup preview only until configured flags and acknowledgements are present
- planned targets separate from current/discovered targets
- NFS/vCenter readiness visible

Controls:

- Console autodiscovery
- Console watch/read-state
- REST/SSH readiness
- Setup preview
- NFS/vCenter readiness

### 7. Firmware / Upgrade Center

Current state:

- iLO firmware
- BIOS
- Smart Array
- Cisco IOS XE
- Cisco ROMMON/bootloader
- ESXi ISO/version
- ONTAP version
- NetApp disk firmware
- NetApp shelf firmware
- NetApp SP/BMC firmware

Desired state:

- baseline compliance visible
- packages/media inventory visible
- waiver status visible
- upgrade plan visible
- upgrade apply placeholder visible and disabled

Controls:

- Run inventory
- Check compliance
- View packages
- Create waiver
- Plan upgrade
- Run upgrade placeholder

### 8. Build Verification

Current state:

- certification state
- lab IP profile status
- credentials redacted presence/compatibility
- MTU and protocol checks
- toolchain availability
- top blockers

Desired state:

- all required stages verified
- certification report export available

Controls:

- Run full verification
- Run scoped verification
- Export certification report

### 9. Action History / Reports

Current state:

- latest report path per action
- latest known report availability
- generated artifact summary

Desired state:

- reports linked next to actions
- action catalog table filterable by device, classification, and availability

Controls:

- Open report path
- Copy command
- Plan action
- Review advanced diagnostics

## Frontend Components

Add and use:

- `CurrentStateBlock`
- `DesiredStateBlock`
- `PlanDiffBlock`
- `ActionButtonRow`
- `ControlSection`
- `ActionCatalogTable`

These components should be compact, scan-friendly, and useful for repeated operator work. Avoid putting the power-user page behind another guided wizard.

## Safety Copy

Use explicit action labels:

- Read only
- Write
- Destructive
- Upgrade
- Direct run disabled
- Copy command
- Plan action
- Blocked by flag

Never show secret values. Configuration presence is enough for credentials and tokens.
