# infra-config-portal

Self-service infrastructure configuration portal for requesting, validating,
approving, executing, and auditing datacenter automation workflows.

The current MVP scaffold lives in `app/`. The running app is a real-lab
operator surface: status, reports, Build Verification, Run Center, Control
Center, Firmware Compliance, and Provider Status report live, live-cached,
historical, or not-checked sources. Mock provider data is reserved for automated
tests and must not be used as a substitute for current lab state.

## Project Layout

```text
infra-config-portal/
  .codex/                  Project-scoped Codex exec automation
  scripts/                 Codex exec wrapper scripts
  Makefile                 Root local and Codex commands
  AGENTS.md                Repo instructions for Codex
  app/                     Current portal MVP scaffold
  reference/               Older notes, experiments, or adjacent ideas
```

## Always Run From Repo Root

Root automation paths such as `.codex/tasks`, `.codex/runs`, and
`.codex/task-queue.md` live at `/home/administrator/infra-config-portal`, not
under `app/`.

Before running root `make` or Codex automation commands:

```bash
cd /home/administrator/infra-config-portal
```

If you are in `/home/administrator/infra-config-portal/app`, move up one level
first. Running root-only targets from `app/` prints:

```text
Run this from /home/administrator/infra-config-portal, not /home/administrator/infra-config-portal/app.
```

## Run Locally

Safe app workflow from the repository root:

```bash
cd /home/administrator/infra-config-portal
make app-start
make app-status
make app-restart
make app-stop
```

The safe workflow is implemented by `./runit`. It records backend and frontend
PID files under `.local/run/`, logs to `.local/log/`, and only stops processes
whose command line and working directory match this app's FastAPI backend or
Vite frontend. It does not kill Firefox, Chrome, Chromium, browser processes,
or arbitrary clients connected to the frontend port.

`make dev` is an alias for `make app-restart`.

Foreground backend-only development:

```bash
cd /home/administrator/infra-config-portal/app
make backend-venv
make backend-run
```

Foreground frontend-only development, in a second terminal:

```bash
cd /home/administrator/infra-config-portal/app
make frontend-install
make frontend-run
```

The backend runs at `http://127.0.0.1:8001`. The Vite frontend runs at
`http://127.0.0.1:5173` and proxies API requests to the backend.

Windows PowerShell does not require Make or bash for the common local gate.
From `app/`, run:

```powershell
.\scripts\windows-doctor.ps1
.\scripts\check-windows.ps1
```

`check-windows.ps1` runs the Windows doctor, backend tests, portable path
checks, frontend component tests, and frontend build with mocked providers.

To include browser-based frontend coverage:

```powershell
.\scripts\ensure-playwright-browsers.ps1 -Install
.\scripts\check-windows.ps1 -E2E
```

If npm is configured with a proxy that times out while fetching package
tarballs, use the script-level bypass for dependency repair:

```powershell
.\scripts\check-windows.ps1 -Install -NoProxy
```

### Operational Mode

The Settings page includes an Operational Mode panel. Runtime options are
`Real Lab Runtime` (`PROVIDER_MODE=local-lab-readwrite`) and
`Read-only Live Checks` (`PROVIDER_MODE=local-readonly`). If the backend is
served with `PROVIDER_MODE=mock`, the UI shows a dev/test banner and Build
Verification cannot certify real results. Selecting a runtime writes ignored
local state under `.local/provider-mode-settings.json` and `.local/app-mode.env`.
Restart the app with `make app-restart` or the command shown in the panel for
the selected mode to take effect.

An explicit shell `PROVIDER_MODE=...` still overrides the local mode file. The
mode selector does not store credentials, does not call providers, and does not
enable workflow-specific apply paths by itself.

Docker Compose:

```bash
cd /home/administrator/infra-config-portal/app
docker compose up --build
```

Compose starts local PostgreSQL, the FastAPI backend, and the Vite frontend in
`PROVIDER_MODE=mock`. This lane is for safe local UI/API development only: it
does not read `.env.local.real-lab`, does not call real provider APIs, and does
not enable real-lab apply paths. The frontend waits for the backend health check
before starting.

Use the `runit`/Make workflow above, not Docker Compose, when intentionally
working in `local-readonly` or `local-lab-readwrite` runtime mode.

## Saved Lab Profiles

Lab Setup lets an operator save named lab address plans, activate a previous
lab, create a new lab, edit the lab subnet/IP plan, and maintain shared global
defaults such as gateway, DNS, NTP, timezone, VLAN, MTU, and vCenter scope.
The active lab selector is visible in the app shell and Lab Setup is the
primary profile editing surface.

Profile state is stored locally under `.local/lab-profiles.json` by default
and is ignored by Git. It stores non-secret address intent only. Selecting a lab
profile does not call providers, does not mutate `.env.local.real-lab`, and does
not enable apply actions; provider environment values still have to match the
selected profile before lab certification can pass.

The active profile drives default values across Dashboard, Lab Setup, Control
Center, Firmware Upgrades, Validation & Reports, Build Verification, NetApp
setup/upgrade, vCenter-NetApp readiness, and workflow registry actions. `/24`
profiles use the high-address layout (`.201` through NetApp `.240-.243`) unless
overridden. `/26` compact profiles use offset defaults from the subnet network
address and keep NetApp/vCenter `not_in_scope` by default. See
`app/docs/lab-profile-examples.md`.

When the active saved profile differs from runtime IP values, the Dashboard
Active Lab strip exposes `Apply Runtime IPs`. It writes only allowlisted
non-secret profile IP/runtime keys to repo-root `.env.local.real-lab`, updates
the running backend process env so the mismatch clears, and still requires a
backend restart before live provider checks rely on startup-loaded settings. It
does not write credentials, call providers, apply device configuration, or
reset hardware.

The API surface is:

- `GET /api/v1/lab/profiles`
- `POST /api/v1/lab/profiles`
- `PUT /api/v1/lab/profiles/{profile_id}`
- `POST /api/v1/lab/profiles/{profile_id}/activate`
- `POST /api/v1/lab/profiles/active/apply-runtime-env`

## Provider Status Preview

The Provider Status page shows real-lab provider cards for HPE iLO/Redfish,
Cisco console, Cisco Ansible SSH, ESXi read-only, and NetApp setup state.
Mock provider cards are test fixtures only. Provider Status does not use mock
health as a fallback; missing live state is reported as not checked. Shared
serial console discovery dynamically inspects `/dev/serial/by-id/*`,
`/dev/ttyUSB*`, `/dev/ttyACM*`, and `/dev/ttyS*` without opening the serial port
during status refresh. Local iLO, ESXi, and Cisco settings are shown
only as configured/missing flags; configured hostnames, usernames, and passwords
are not returned in provider status payloads.

Canonical real-lab tooling is:

- Cisco first contact: ser2net/Opengear or local serial through the app console
  workflow.
- Cisco normal management: Ansible `cisco.ios`, Netmiko, and pyATS/Genie
  parsing after console bootstrap configures management SSH.
- HPE/iLO: Redfish plus HPE iLOrest.
- ESXi: Kickstart plus `govc`.
- NetApp: `netapp-ontap` Python client plus ONTAP REST.
- Verification: Build Verification consumes those outputs and classifies
  readiness, blockers, stale configuration, and failures.

The HPE iLO Baseline Configuration preview is available at
`GET /api/v1/providers/hpe-ilo/baseline-preview`, with connection-focused
readiness at `GET /api/v1/providers/hpe-ilo/readiness`. These endpoints derive
KitID, SupportUnit, subnet mask, gateway, DomDC, discovery `.21` through `.29`,
expected users, license status, SNMP/SNMPv3, alert destinations, dedicated-port
IPv6, SNTP/time, and reset handling from the active lab profile and cached
read-only iLO evidence only. They do not run Redfish, apply configuration, write
users/SNMP/time settings, expose secret values, or reset hardware; `apply_enabled`
is always false in this first preview pass.

The `netapp-ontap` setup preview displays the target addressing plan,
console/bootstrap readiness checklist, disabled ONTAP API readiness,
placeholder upgrade path, cluster/SVM/iSCSI/NFS intent, and artifact/report
placeholders. The structured plan preview is available at
`GET /api/v1/providers/netapp-ontap/plan-preview`; it is generated from local
planned values and makes no ONTAP write calls. Run Center shows the same NetApp
payload with explicit read-only console discovery/read-state controls when
real-lab mode and acknowledgements are active. `GET /api/v1/providers/netapp-ontap/artifacts`
returns test-fixture placeholder metadata only when the backend is explicitly in
test mode; real runtime uses generated reports and current-state artifacts
instead. `GET /api/v1/providers/artifacts` aggregates provider-scoped
artifact metadata, and the Reports / Artifacts page makes the NetApp placeholder
discoverable outside Run Center. `GET /api/v1/providers/netapp-ontap/setup-preview`
exposes the setup intent, missing setup fields, wizard/API path options, exact
proposed changes, apply command, and pre-apply address conflict scan
requirement. `POST /api/v1/providers/netapp-ontap/setup-apply` is guarded and
refuses unless `NETAPP_SETUP_APPLY=true`,
`NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP"`, and
`NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true` are present and the setup intent and
fresh address scan pass. `GET /api/v1/providers/netapp-ontap/upgrade-readiness`
compares an unknown or locally configured placeholder ONTAP version with
sanitized media inventory metadata only; it does not query a controller and
keeps upgrade/apply disabled. ONTAP Upgrade Center endpoints under
`/api/v1/providers/netapp-ontap/ontap-upgrade/*` provide inventory, plan,
validation, and guarded apply report paths. Upgrade apply refuses unless setup
is verified, an image/package and target are selected, validation passes or an
explicit waiver is present, and `NETAPP_ONTAP_UPGRADE_APPLY=true` with
`NETAPP_ONTAP_UPGRADE_CONFIRM="UPGRADE ONTAP"` is set. `GET /api/v1/providers/netapp-ontap/console-readiness`
returns console/bootstrap prerequisites and expected prompt/state guidance.
`GET`/`POST /api/v1/providers/netapp-ontap/console-discovery` and
`GET`/`POST /api/v1/providers/netapp-ontap/console-read-state` support the
real-lab serial path; the POST actions open ranked local console candidates and
send newline and carriage return wake bytes only. They do not send
credentials, commands, Ctrl+Z, break, boot menu selections, boot interruption,
SP APIs, SSH, or ONTAP API calls.
`GET`/`POST /api/v1/providers/netapp-ontap/live-state` and `POST
/api/v1/providers/netapp-ontap/validate-setup` read and persist redacted
runtime state. `NETAPP_CONSOLE_PORT` is an optional hint only; discovered port,
baud, confidence, last seen, and source are saved in local app state and reports.
`GET /api/v1/providers/netapp-ontap/nfs-vcenter-readiness` writes a
preview-only NFS/vCenter readiness report with no ONTAP, vCenter, or ESXi
apply action. `GET /api/v1/providers/netapp-ontap/observations` and `PUT
/api/v1/providers/netapp-ontap/observations` provide a process-local evidence
capture for bounded manual readiness observations; these notes reject
secret-shaped text, are not persisted to artifacts, and are not sent to any
NetApp device.
`GET /api/v1/providers/netapp-ontap/readiness-comparison` compares planned
targets with those manual observations only; it does not discover or validate
live device state. Missing required manual checks are reported as unknown or
blocking rows, while optional Controller B console observation is reported as a
warning when absent. The console readiness summary keeps required and optional
observation counts separate. `NETAPP_CONFIGURED` is legacy/advanced context
only; Build Verification prefers live verified NetApp state and does not require
manual env state tracking. The portal must not create an ONTAP cluster, change
IPs, create SVMs or LIFs, create volumes, upgrade ONTAP, reboot controllers,
wipe disks, or apply NetApp changes.

ESXi and Cisco management IPs can be recorded as planned targets without being
treated as reachable devices. Keep `ESXI_CONFIGURED=false` until ESXi
management networking is installed and keep `CISCO_MGMT_CONFIGURED=false` until
console bootstrap has configured Cisco management IP/SSH. Provider status and
provider-smoke skip those network probes while the flags are false; Cisco
console discovery still runs.

Optional local isolated-real-lab values live in `.env.local.real-lab`, which is ignored
by Git and must not be committed. Create it with:

```bash
./scripts/setup-real-lab-env.sh
```

Manual local-readonly smoke:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

iLO-only local-readonly smoke:

```bash
PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=ilo-redfish make provider-smoke
```

iLO-only local-lab-readwrite smoke:

```bash
make provider-lab-ilo-reachability
make provider-lab-ilo-authentication
make provider-lab-ilo-readiness
make provider-lab-ilo-inventory
make provider-lab-hpe-storage-discovery
make provider-lab-hpe-raid-discovery
make provider-lab-hpe-raid-plan
```

NetApp-only real-run readiness, with no ONTAP probes or apply actions:

```bash
PROVIDER_MODE=local-readonly make netapp-real-readiness
```

NetApp real-lab console/NFS readiness targets, still with no ONTAP/vCenter/ESXi
apply actions:

```bash
make provider-lab-serial-console-discovery
make provider-lab-netapp-console-autodiscovery
make provider-lab-netapp-console-discovery
make provider-lab-netapp-console-read-state
make provider-lab-netapp-live-state
make provider-lab-netapp-validate-setup
make provider-lab-netapp-nfs-vcenter-readiness
```

NetApp setup and ONTAP Upgrade Center report targets, with apply still disabled
unless exact flags are intentionally present:

```bash
make provider-lab-netapp-setup-baseline
make provider-lab-netapp-setup-plan
make provider-lab-netapp-setup-preview
make provider-lab-netapp-setup-apply
make provider-lab-netapp-post-setup-validation
make provider-lab-netapp-ontap-upgrade-inventory
make provider-lab-netapp-ontap-upgrade-plan
make provider-lab-netapp-ontap-upgrade-validate
make provider-lab-netapp-ontap-upgrade-apply
```

Lab validation and vCenter-NetApp handoff/readiness reports, with apply still
disabled:

```bash
make provider-lab-validation
make provider-lab-vcenter-netapp-readiness
make provider-lab-vcenter-netapp-datastore-plan
```

These targets write `lab-validation-handoff-report.md`,
`vcenter-netapp-readiness-report.md`, and
`vcenter-netapp-datastore-plan-report.md` under `artifacts/codex-runs/`. They
do not run ONTAP, vCenter, ESXi, datastore, storage provisioning, reboot, wipe,
or upgrade write actions. vCenter-NetApp readiness remains blocked by the
NetApp setup/NFS prior stage while the console shows `cluster_setup_wizard`.

The console targets write redacted reports under `artifacts/codex-runs/` and
use a configured `NETAPP_CONSOLE_PORT` as a ranking hint when set, then
auto-discover `/dev/serial/by-id/*`, `/dev/ttyUSB*`, `/dev/ttyACM*`, and
`/dev/ttyS*`. Operators do not copy discovered console ports or configured
state back into `.env.local.real-lab`; the app persists last-known-good state in
`artifacts/codex-runs/netapp-console-last-known-good-redacted.json`,
`artifacts/codex-runs/netapp-live-state-report.md`, and
`artifacts/codex-runs/netapp-state-automanagement-report.md`. The current lab
can run with only one NetApp management port connected; that is enough for
initial console/API bring-up, but full HA/SP/node/SVM/NFS validation remains
blocked until the remaining management/data paths are connected and configured.

The backend loads local provider values from `.env.local.real-lab`, but ignores
`PROVIDER_MODE` from that file; the running app defaults to
`local-lab-readwrite`, while test targets set `PROVIDER_MODE=mock` explicitly.
Plain `make provider-smoke` runs in mock mode and skips probes. With explicit
`PROVIDER_MODE=local-readonly`, the smoke command writes sanitized JSON and
Markdown summaries under ignored `artifacts/real-lab/`, skips planned but not
configured ESXi/Cisco management targets gracefully, and must not print
passwords. `LAB_CLOSED_LOOP_ACK=YES` and `LAB_READONLY_ACK=YES` are required for
real read-only probes. Set `PROVIDER_SMOKE_PROVIDERS=ilo-redfish` to run only
the iLO GET-only Redfish smoke without Cisco or ESXi probes.

`PROVIDER_MODE=local-lab-readwrite` is separate from mock and local-readonly.
It requires `LAB_ENVIRONMENT=isolated-real-lab`,
`LAB_ACKNOWLEDGE_REAL_HARDWARE=true`,
`LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true`,
`LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true`, and
`LAB_ACKNOWLEDGE_LAB_ONLY=true` in `.env.local.real-lab`. Allowlisted lab
workflow categories can run only through explicit workflow steps. Power,
firmware update, and factory reset categories remain blocked unless their
specific `LAB_ALLOW_*` flags are enabled.

`make provider-lab-hpe-storage-discovery`,
`make provider-lab-hpe-raid-discovery`, and
`make provider-lab-hpe-raid-plan` use real iLO Redfish inventory in
`local-lab-readwrite` mode, report HPE Smart Array/controller, drive, and
logical drive details when Redfish exposes them, and write/update
`artifacts/codex-runs/hpe-raid-discovery-report.md` and
`artifacts/codex-runs/hpe-raid-plan-report.md`. The RAID plan target saves a
default ESXi layout only when no RAID intent exists: RAID1 for ESXi OS on the
first two discovered bays and RAID6 for the remaining bays.

The real HPE RAID apply path uses Redfish SmartStorageConfig settings because
`ssacli`/`hpssacli` is not required on the app host. It remains gated by
`PROVIDER_MODE=local-lab-readwrite`, the real-lab acknowledgement flags, a saved
destructive RAID intent, `HPE_RAID_ALLOW_DESTRUCTIVE=true`, and the exact
confirmation phrase. The apply target records before/after state and writes
`artifacts/codex-runs/hpe-raid-apply-report.md`.

```bash
HPE_RAID_ALLOW_DESTRUCTIVE=true \
HPE_RAID_APPLY_CONFIRM="APPLY HPE RAID PLAN" \
make provider-lab-hpe-raid-apply
```

The Provider Status iLO section also exposes an HPE Storage / RAID setup panel.
It reads cached Redfish storage discovery, saves a desired RAID intent, and
shows current layout versus planned ESXi layout impact. The panel shows RAID
apply availability and last real apply state; destructive execution still runs
through the explicit terminal target above.

After RAID validation succeeds, the ESXi boot workflow can serve an ISO from
`MEDIA_INVENTORY_DIRS`, insert it through iLO VirtualMedia, set one-time boot,
and run the controlled reset. The default ISO selection prefers HPE ESXi 8.0.3
when present. These targets write reports under `artifacts/codex-runs/`:

```bash
make provider-lab-esxi-install-readiness
make provider-lab-esxi-media-url
make provider-lab-esxi-insert-virtual-media
make provider-lab-esxi-one-time-boot
make provider-lab-esxi-reset-installer-boot
make provider-lab-esxi-detect-installer
```

Cisco console and Ethernet bootstrap readiness remains separate from ESXi. It
detects a serial console adapter, performs newline-only prompt readiness, and
reports management Ethernet/SSH/SCP bootstrap state without sending
configuration commands:

```bash
make provider-lab-cisco-console-ethernet-readiness
```

The Cisco real-lab console workflow performs a preflight claim before opening
the selected adapter. It checks the configured `/dev/serial/by-id/...` path and
the resolved `/dev/ttyUSB*` path for owning processes, and reports ownership in
the run artifacts. In `PROVIDER_MODE=local-lab-readwrite`, setting
`CISCO_CONSOLE_RECLAIM=true` allows the workflow to terminate stale
`screen`, `picocom`, `minicom`, and `python*` serial holders for the selected
console and remove stale `LCK..tty*` lock files before reopening the port.
Configuration apply still requires the explicit `--apply` argument.

Full lab rebuild has separate report-only and real execution paths:

```bash
make provider-lab-full-rebuild-summary
make provider-lab-full-rebuild
make provider-lab-build-verification
make provider-lab-toolchain-check
```

`provider-lab-full-rebuild-summary` refreshes dashboard summaries without live
device calls. `provider-lab-full-rebuild` runs the live local lab path with
`PROVIDER_MODE=local-lab-readwrite` and `.env.local.real-lab`; it calls Cisco,
iLO, RAID, and ESXi stages and records real blockers. Build verification writes
`artifacts/codex-runs/build-verification-report.md` with credential, MTU,
protocol, port, checklist, failure-classification, and next-action checks.
Toolchain check writes `artifacts/codex-runs/toolchain-availability-report.md`
with local package and CLI availability only; it does not contact real devices.
Build verification stages unresolved work as `blocked_by_prior_stage`,
`not_configured_yet`, `stale_config`, `operator_action_required`, `warning`,
`hard_fail`, or `passed`, and also writes classification, lab-IP hardening, and
failure-case hardening reports under `artifacts/codex-runs/`.

The NetApp-only readiness command writes `netapp-readiness-*` artifacts under
the same ignored directory and never contacts ONTAP, SP, console, SSH, storage,
upgrade, reboot, wipe, or apply endpoints.

## Tests And Checks

From the repository root:

```bash
make test
make lint
```

`make test` runs backend pytest and the frontend TypeScript/build check.
`make lint` runs backend Ruff only when it is installed in `app/backend/.venv`,
checks for Windows/Linux-portable repository paths, then runs the frontend
build/type check.

CI runs the same Linux Make gate on Ubuntu and the PowerShell gate on Windows
through `.github/workflows/ci.yml`.

On Windows without Make/bash, run the equivalent PowerShell gate from `app/`:

```powershell
.\scripts\check-windows.ps1
.\scripts\check-windows.ps1 -E2E
```

The backend pytest suite includes a mock-only VM lifecycle smoke test. To run
that smoke coverage directly:

```bash
cd /home/administrator/infra-config-portal/app/backend
PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py
```

The smoke test uses FastAPI `TestClient`, an in-memory SQLite database, and the
mock provider adapters. It verifies health, draft creation and patching,
submission, approval, readiness summaries, dry-run planning, mock execution to
completion, request rejection, audit events for major transitions, execution-before-plan
rejection, stale-plan invalidation after an execution-affecting edit, and
completed-request cancellation rejection. It does not start a backend server
and must remain `PROVIDER_MODE=mock`.

When a task changes visible frontend UI, validate the running page with
screenshots when practical. Capture the changed page or section plus a relevant
validation, empty, blocked, or error state when applicable. Store screenshots
only in ignored local paths such as `artifacts/screenshots/`, and do not commit
them unless the project explicitly introduces committed UI snapshots. If
screenshots are skipped, document why and describe the manual UI checks.

## Codex Exec Mode

This repository includes repeatable non-interactive Codex workflows under
`.codex/`.

Run these commands from `/home/administrator/infra-config-portal`.

Run the audit task:

```bash
make codex-audit
```

Run a specific task:

```bash
make codex-task TASK=.codex/tasks/001-backend-vm-request-lifecycle.md
```

Run the next unchecked task from `.codex/task-queue.md`:

```bash
make codex-next
```

Resume the most recent exec session:

```bash
make codex-resume
```

The wrapper scripts run `codex exec` from the repository root with safe
defaults: `CODEX_SANDBOX_MODE=workspace-write`,
`CODEX_APPROVAL_POLICY=never`, and workspace-write network access disabled.
They pass approval policy with
`-c "approval_policy=\"${CODEX_APPROVAL_POLICY}\""` because this installed CLI
does not accept `--ask-for-approval`. The root `Makefile` exports those safe
defaults for `make codex-*` commands; callers may override them explicitly in
the command environment.

If local bwrap sandboxing fails before shell execution, the explicitly
acknowledged fallback command is:

```bash
CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND make codex-next
```

`danger-full-access` is never the default. Use it only on an isolated
development machine with no real infrastructure credentials, no secrets, no
production SSH keys, and no access to real vSphere, ESXi, iLO, NetApp,
switches, DNS, IPAM, storage, or production networks. Do not export
`CODEX_SANDBOX_MODE=danger-full-access` globally; set it only on the single
fallback command that requires it.

## Safety Rules

- Keep `PROVIDER_MODE=mock` for automated tests only.
- Use `PROVIDER_MODE=local-readonly` only for explicit local iLO, Cisco, and
  ESXi preview probes, or NetApp readiness-only reporting, on an isolated lab
  machine with `LAB_CLOSED_LOOP_ACK=YES` and `LAB_READONLY_ACK=YES`.
- Do not add real credentials, IPs, hostnames, tokens, passwords, or customer
  data.
- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or source-of-truth API calls.
- Do not use `--yolo` or sandbox bypass flags.
- Do not use `danger-full-access` by default; it is allowed only through the
  explicit Codex wrapper environment variables and acknowledgement above.
- Future real provider adapters must require explicit configuration, dry-run or
  planning, approval, and audit logging.
