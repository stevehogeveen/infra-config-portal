# infra-config-portal

## SPP Firmware Installation

Check firmware supports separately reviewed iLO 5 1.48 and 3.19 updates from the
selected SPP, with signed-package verification and independent completion readback.
See [Firmware installation](docs/firmware-installation.md) for the operator flow,
offline tests and model-specific requirements for future cumulative SPP support.

[Blocker guidance](docs/blocker-guidance.md) describes the additive remediation
contract and shorter version-specific iLO confirmation. Guidance never clears
hardware faults or authorizes retries of uncertain submissions.

The [whole-SPP backend foundation](docs/spp-update-backend.md) provides validated
review/progress contracts, a vendor repository-report parser and an offline-tested
durable execution worker with an injectable adapter. It does not yet
expose whole-SPP installation endpoints; the existing iLO workflow remains active.

## Rack Workbench

Rack home (`/simple`) offers Rack and List views over the same kit equipment.
The Overview tab offers the next setup action; Edit equipment holds placement,
model and capacity settings. Server connection setup uses the existing saved
iLO settings and separate, explicitly initiated Checks workflow.
Overview readiness is currently unverified, not aggregated provider evidence.
It must not be interpreted as successful firmware, ESXi or Windows validation.
Unsaved rack drafts survive navigation in browser storage, scoped to the kit;
Save a copy also persists them to the server. No hardware changes run automatically.

Self-service infrastructure configuration portal for requesting, validating,
approving, executing, and auditing datacenter automation workflows.

The first MVP implements one safe workflow and a real-lab operator surface:

- Deploy VM from vSphere template
- Store requests locally
- Validate user input and mock source-of-truth data
- Require approval before planning and execution
- Report readiness, blockers, and the next safe action
- Keep VM lifecycle execution in local dry-run/test-fixture adapters until real provider lanes are approved
- Record audit events for each important transition

Operator status surfaces use live, live-cached, historical, or not-checked
source metadata. Mock provider data is for automated tests only and is not used
as a substitute for current lab state. Real provider actions remain gated by
explicit runtime mode, acknowledgements, dry-run/read-only behavior, and
workflow-specific safety checks.

## Rack Drive Plans

The beside-rack iLO configurator's Drives tab saves allocation intent and previews
the saved plan for the selected device. Editing an allocation invalidates its
preview; unresolved bay IDs block saving and previewing. Saved roles are plans,
not proof that RAID volumes or raw passthrough already exist.

Devices are identified by inventory ID, not IP address. The Drives tab resolves
the current saved access settings and rejects save/preview when those settings
change. Update the device's Access tab after an address change, then reload
inventory and run a read-only check. Historical handoff addresses are not defaults.

Apply remains visibly blocked here because the existing apply endpoint uses the
default lab target. It needs device-bound preview and explicit confirmation before
this panel can enable controller writes.

## Project Layout

The first queued automation workflow is available in the rack's Checks tab.
See [automation architecture and startup](docs/automation-architecture.md) for
the optional Redis/RQ worker stack, Ansible playbook, and migration boundaries.
The default remains mock mode.

```text
infra-config-portal/
  README.md                 Workspace note
  reference/                Prior notes or related ideas
  app/
    backend/                FastAPI API, SQLAlchemy models, tests
    frontend/               React + Vite + TypeScript UI
    docs/                   Architecture, workflow, security, providers
    docker-compose.yml      Local dev services
    .env.example            Safe local runtime defaults
    Makefile                Common local tasks
```

## Backend Quick Start

Safe start/stop/restart from the app directory:

```bash
cd /home/administrator/infra-config-portal/app
make start
make status
make restart
make stop
```

These targets call the repository-root `./runit` supervisor. It writes PID files
under `.local/run/`, logs under `.local/log/`, and only stops app-owned FastAPI
and Vite dev server processes after validating their command lines and working
directories. It does not kill Firefox, Chrome, Chromium, browser processes, or
arbitrary clients connected to `5173`.

Foreground backend-only development:

```bash
cd /home/administrator/infra-config-portal/app
make backend-venv
make backend-test
make backend-run
```

The backend defaults to SQLite at `backend/.local/infra_config_portal.db`.

API health check:

```bash
curl http://127.0.0.1:8001/health
```

## Tests And Smoke Coverage

From the repository root:

```bash
make test
make lint
```

`make test` runs backend pytest and the frontend TypeScript/build check.
`make lint` runs shell syntax checks, checks for Windows/Linux-portable
repository paths, backend Ruff when installed in `backend/.venv`, and the
frontend build/type check.
Both root gates also run the fast frontend component/server-render checks:

```bash
cd app/frontend
npm run test:component
```

These cover shared UI components without launching a browser, so Playwright can
stay focused on real navigation, guarded-run, persistence, and visual flows.
On Windows without Make, `.\scripts\check-windows.ps1` runs the same mocked
backend tests, portable path check, frontend component tests, and frontend
build from `app/`.

For faster Windows iteration during visual/backend feature work, use the
diff-aware verification lane:

```powershell
cd C:\path\to\infra-config-portal\app
.\scripts\fast-verify.ps1
```

Use `.\scripts\fast-verify.ps1 -WhatIfOnly` to preview the targeted checks, and
use `.\scripts\fast-verify.ps1 -Full` before handoff when you want the full
frontend/backend gate. See `docs/testing-acceleration.md` for the tiered test
strategy, visual-regression path, and AI-assisted triage plan.
Each executed run writes its selected plan to
`artifacts/codex-runs/fast-verify-plan.json`. If a step fails, fast-verify
also creates a redacted advisory QA packet unless you pass `-NoFailurePacket`.
The plan includes `step_details` with the selected step id, routing reason, and
command family so humans and AI triage can see why the compact lane ran.
Validate the saved plan contract with `.\scripts\fast-verify.ps1 -ValidatePlan`.
API route, schema, or workflow-registry changes also run a generated OpenAPI
contract probe. Run it directly with:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\openapi_contract_probe.py
```

The probe writes `artifacts/codex-runs/openapi-contract-probe.json` and checks
OpenAPI operation IDs, workflow action endpoint wiring, and guard metadata
without calling endpoints or running workflow actions.
CI runs the same family of gates on push/PR: Linux `make test`/`make lint`,
Windows `check-windows.ps1 -E2E`, and Windows `fast-verify.ps1 -Full`, with
fast-verify and failure-packet artifacts uploaded for review.
Validate all local QA artifact contracts together with:

```powershell
.\scripts\qa-artifact-health.ps1
```

The same health gate validates the QA capability audit artifact when present.
Refresh dry-run plans plus the capability audit without running tests or
touching hardware:

```powershell
.\scripts\qa-artifact-health.ps1 -GenerateMissingPlans
```

Real-lab smoke verification is a separate on-demand lane. Preview it first:

```powershell
.\scripts\hardware-smoke.ps1 -WhatIfOnly
```

The preview writes `artifacts/codex-runs/hardware-smoke-plan.json`; validate it
without touching hardware:

```powershell
.\scripts\hardware-smoke.ps1 -ValidatePlan
```

Then run the default read-only provider smoke lane only after confirming the
lab is safe to probe:

```powershell
.\scripts\hardware-smoke.ps1 -AcknowledgeReadOnly
```

Use `-Providers ilo-redfish` to narrow the run, or add
`-IncludeOperatorSweep` for the broader read-only workflow-action evidence
gate. The script refuses `local-lab-readwrite` unless `-AllowWriteMode` is
explicitly present; destructive workflows still require their own exact gates.

After a failing pytest, Playwright, workflow, or hardware-smoke run, create a
redacted advisory packet for AI-assisted triage:

```powershell
.\scripts\qa-failure-packet.ps1 -Note "what looked wrong"
```

The packet is written under
`artifacts/codex-runs/qa-failure-packets/latest.json` and `.md`. It collects
recent local failure evidence and generates an AI-ready prompt, but it does not
call an external AI service, run tests, trigger workflow actions, or touch
hardware. The packet also includes structured `advisory_triage` with the
probable failure area, evidence kinds, and a safe verification command. Validate
the latest packet contract with:

```powershell
.\scripts\qa-failure-packet.ps1 -ValidateLatest
```

The backend pytest suite includes a local mock VM lifecycle smoke test. Run only
that smoke test with:

```bash
cd /home/administrator/infra-config-portal/app/backend
PROVIDER_MODE=mock .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py
```

The smoke test uses FastAPI `TestClient`, an in-memory SQLite database, and mock
provider adapters only. It covers health, VM request creation, draft patching,
submit, approval, dry-run planning, mock execution to completed, audit events,
readiness checks, request rejection, execution-before-plan rejection, stale-plan
invalidation after an execution-affecting edit, and completed-request
cancellation rejection.

Keep `PROVIDER_MODE=mock`. The smoke test must not call vCenter, ESXi, iLO,
Redfish, NetApp, switches, DNS, IPAM, storage, AWX, Terraform, OpenTofu,
NetBox, Nautobot, PowerCLI, govc, OVF Tool, or any lab/production
infrastructure.

For changes to visible frontend pages, run the app locally and capture
screenshots when practical. Include the changed page or section and a relevant
validation, empty, blocked, or error state when applicable. Save screenshots
only under ignored local paths such as `artifacts/screenshots/`; do not commit
them unless the project explicitly expects committed UI snapshots. If
screenshots are skipped, note why and describe the manual UI checks performed.

## Frontend Quick Start

Foreground frontend-only development, in a second terminal:

```bash
cd /home/administrator/infra-config-portal/app
make frontend-install
make frontend-run
```

The Vite dev server runs at `http://127.0.0.1:5173` and proxies API requests
to `http://127.0.0.1:8001`.

On Windows PowerShell, use the native scripts instead of the Unix-oriented
Make/runit startup path. For a fresh one-command launch:

```powershell
cd C:\path\to\infra-config-portal\app
.\scripts\start-lab-builder.ps1
```

The launcher starts hidden backend and frontend processes, waits for both HTTP
surfaces, opens the Rack home at `http://127.0.0.1:5173/simple`, and records only the processes
it owns under repo-root `.local\windows-runtime`. It uses an explicit `-Mode`
first, then an existing `PROVIDER_MODE`, then the mode saved by the app in
`.local\app-mode.env`, and otherwise fails safely to `mock`.

Stop only that owned Windows session with:

```powershell
.\scripts\stop-lab-builder.ps1
```

Use separate PowerShell windows when foreground logs or independent process
control are useful:

```powershell
cd C:\path\to\infra-config-portal\app
.\scripts\windows-doctor.ps1

.\scripts\ensure-backend-venv.ps1
.\scripts\test-backend.ps1
.\scripts\start-backend.ps1
```

Then install and start the frontend:

```powershell
cd C:\path\to\infra-config-portal\app
.\scripts\ensure-frontend-deps.ps1
.\scripts\start-frontend.ps1
```

Run the Windows quality gate without Make/bash:

```powershell
.\scripts\check-windows.ps1
```

Include browser tests when Playwright browsers are installed:

```powershell
.\scripts\check-windows.ps1 -E2E
```

Install the Playwright browser used by the e2e suite:

```powershell
.\scripts\ensure-playwright-browsers.ps1 -Install
```

To pass specific pytest arguments, provide each argument as its own value:

```powershell
.\scripts\check-windows.ps1 -PytestArgs "tests/test_portable_paths.py", "-q"
```

To point the frontend at a different backend or port, pass explicit values:

```powershell
.\scripts\start-frontend.ps1 -Port 4173 -ProxyTarget http://127.0.0.1:8001
```

If dependencies are missing and network access is available, the start scripts
can repair them directly:

```powershell
.\scripts\start-backend.ps1 -Install
.\scripts\start-frontend.ps1 -Install
.\scripts\check-windows.ps1 -Install
.\scripts\check-windows.ps1 -Install -E2E
```

If npm is configured with a proxy that can reach metadata but times out on
package tarballs, bypass it for this install:

```powershell
.\scripts\ensure-frontend-deps.ps1 -NoProxy
.\scripts\start-frontend.ps1 -NoProxy
.\scripts\check-windows.ps1 -Install -NoProxy
```

To run the backend on a different local port:

```powershell
.\scripts\start-backend.ps1 -Port 8010
.\scripts\start-frontend.ps1 -ProxyTarget http://127.0.0.1:8010
```

The one-command equivalent is:

```powershell
.\scripts\start-lab-builder.ps1 -BackendPort 8010 -FrontendPort 5174 -NoBrowser
```

For LAN access from another computer on the same trusted lab network, bind only
the frontend to all interfaces and keep the backend loopback-protected behind
the Vite proxy:

```bash
cd /home/administrator/infra-config-portal
make app-restart-lan
```

Then open `http://<this-host-lan-ip>:5173` from the other computer. If the
auto-detected address is not the one you want shown in the start output, pass
`PUBLIC_APP_HOST=<this-host-lan-ip>`. Expose the backend itself only when you
explicitly need direct API access on a trusted lab network:
`BACKEND_HOST=0.0.0.0 FRONTEND_HOST=0.0.0.0 make app-restart`.

The VM request list shows filterable request status, ownership, readiness, and
blocked indicators. The request detail view shows readiness, blockers,
lifecycle actions, approval, mock execution, cancellation, request-scoped audit
events, draft editing, notes updates for editable pre-execution requests, and
mock artifact/report cards. Run Center shows pending requests, local workflow
runs, mock stage status, report handoff links, and review-before-execute state.
Audit Events can be filtered by request ID, workflow run ID, event type,
status, link scope, and text payload. Media Inventory shows sample metadata by
default, or placeholder-only metadata from explicitly configured
`MEDIA_INVENTORY_DIRS`.

Lab Setup can save named lab address plans, activate a prior lab, create a new
lab, edit the lab subnet/IP plan, maintain shared global defaults, and review
earlier profile versions. Profile state is local-only under
`.local/lab-profiles.json` by default. It stores address intent, rejects
secret-shaped text, and does not call providers, rewrite `.env.local.real-lab`,
or enable apply actions.

## Docker Compose

```bash
cd /home/administrator/infra-config-portal/app
docker compose up --build
```

Compose starts PostgreSQL, the FastAPI backend, and the Vite frontend in
`PROVIDER_MODE=mock`. This lane is for safe local UI/API development only: it
does not read `.env.local.real-lab`, does not call real provider APIs, and does
not enable real-lab apply paths. The image preserves the repository layout used
by shared config and scripts, while repo-root `.local` and `artifacts` are
mounted so saved setups and evidence survive rebuilds. Frontend API calls stay
same-origin through the Vite proxy, and a named volume keeps container
`node_modules` out of the Windows checkout. The frontend waits for the backend
health check before starting.

Use the `runit`/Make workflow, not Docker Compose, when intentionally working
in `local-readonly` or `local-lab-readwrite` runtime mode.

## MVP API Flow

1. `POST /api/v1/requests/vm-deploy`
2. `GET /api/v1/requests/{id}/readiness`
3. `POST /api/v1/requests/{id}/submit`
4. `POST /api/v1/requests/{id}/approve`
5. `POST /api/v1/requests/{id}/plan`
6. `GET /api/v1/requests/{id}/readiness`
7. `POST /api/v1/requests/{id}/execute`
8. `GET /api/v1/workflow-runs`
9. `GET /api/v1/media-inventory`
10. `GET /api/v1/audit-events`

The readiness endpoint is read-only. It returns readiness flags, structured
`blockers` and `warnings` with `code`, `message`, `severity`, and `action`, a
machine-friendly `next_action`, and a short operator summary. It does not create
plans, execute workflows, write audit events, or call provider adapters.

The media inventory endpoint is metadata-only. It does not copy, mount, parse,
deploy, or execute local media files, and it redacts actual local filenames.

## Provider Status Preview

Provider Status shows real-lab provider health for HPE iLO / Redfish, Cisco
console, Cisco Ansible SSH, ESXi read-only checks, and NetApp setup planning.
Mock provider cards are test fixtures only and are hidden from real-lab runtime.
Missing live state is reported as not checked rather than replaced with mock
health. Cisco console
discovery is read-only filesystem inspection of `/dev/serial/by-id/*`,
`/dev/ttyUSB*`, and `/dev/ttyACM*`; it does not open serial ports or send
commands during discovery.
iLO, ESXi, and Cisco management configuration is reported only as
configured/missing flags. The API does not return configured host, username, or
password values.

`netapp-ontap` setup remains plan/preview only. The provider page displays the
planned Controller SP, cluster management, node management, SVM management, and
iSCSI LIF addresses separately from current/discovered targets. Current targets
come from live verification and runtime state, not from manual env tracking.
The page also shows separate setup and upgrade readiness, bootstrap/API/upgrade
readiness, cluster/SVM/LIF intent, storage/iSCSI intent, and artifact/report
placeholders. The structured
`GET /api/v1/providers/netapp-ontap/plan-preview` endpoint returns the same
plan-only contract for Run Center and future report generation. Run Center
renders it as a preview-only section with refresh only; it has no NetApp apply,
confirm, start, execution, upgrade, reboot, wipe, create, or configuration
control. `GET /api/v1/providers/netapp-ontap/artifacts` returns test-fixture
placeholder metadata only when the backend is explicitly in test mode; real
runtime uses generated current-state and evidence artifacts instead.
`GET /api/v1/providers/artifacts` aggregates provider
artifact metadata, and the Reports / Artifacts page exposes the NetApp
placeholder outside Run Center with provider/kind/status filters.
`GET /api/v1/providers/netapp-ontap/upgrade-readiness` is offline-only: it uses
an unknown or locally configured placeholder current ONTAP version and sanitized
media inventory metadata to preview candidate media and upgrade path shape.
`GET /api/v1/providers/netapp-ontap/setup-preview` exposes setup intent,
remediation items, wizard/API path options, exact proposed changes, apply
command, and pre-apply address conflict scan requirements. `POST
/api/v1/providers/netapp-ontap/setup-apply` is guarded and refuses unless
`NETAPP_SETUP_APPLY=true`, `NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP"`,
and `NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true` are present and the setup intent
and fresh address scan pass. ONTAP Upgrade Center endpoints under
`/api/v1/providers/netapp-ontap/ontap-upgrade/*` provide inventory, plan,
validation, and guarded apply report paths. Upgrade apply refuses unless setup
is verified, an image/package and target are selected, validation passes or an
explicit waiver is present, and `NETAPP_ONTAP_UPGRADE_APPLY=true` with
`NETAPP_ONTAP_UPGRADE_CONFIRM="UPGRADE ONTAP"` is set.
`GET /api/v1/providers/netapp-ontap/console-readiness` is manual/offline only:
it lists prerequisites, manual operator steps, expected prompts/states, and
disabled bootstrap actions without opening serial ports or sending commands.
`GET`/`POST /api/v1/providers/netapp-ontap/live-state` and `POST
/api/v1/providers/netapp-ontap/validate-setup` persist redacted live state,
including discovered console port, baud, confidence, last seen, and configured
state evidence. `NETAPP_CONSOLE_PORT` is an optional hint only, and
`NETAPP_CONFIGURED` is legacy/advanced context only.
`GET /api/v1/providers/netapp-ontap/observations` and `PUT
/api/v1/providers/netapp-ontap/observations` capture bounded operator
readiness observations in a process-local mock store only and reject
secret-shaped note text. Run Center shows the same local notes in the
console/bootstrap section and warns operators not to paste passwords, tokens,
or raw configs.
`GET /api/v1/providers/netapp-ontap/readiness-comparison` compares planned
targets with those operator observations only and reports matched, unknown,
warning, and blocked manual readiness rows without live discovery. Optional Controller B
console observation is surfaced as a warning when it has not been recorded, and
the console readiness summary separates required and optional observation
counts. Cluster management not configured, node management not configured, SVM
management planned but not live, iSCSI LIF range planned but not live, missing
credentials, and missing `LAB_READONLY_ACK=YES` are reported as setup/upgrade
readiness blockers where applicable.
No NetApp Service Processor, SSH, storage provisioning, LIF creation, upgrade,
reboot, wipe, or apply call is made. ONTAP API validation is read-only and only
runs through explicit live-state/setup-validation actions.

ESXi and Cisco management IPs can be planned without being treated as reachable
targets. Keep `ESXI_CONFIGURED=false` until ESXi management networking is
installed and keep `CISCO_MGMT_CONFIGURED=false` until console bootstrap has
configured Cisco management IP/SSH. Provider status and provider-smoke skip
those network probes while the flags are false; Cisco console discovery still
runs.

The Cisco Setup Readiness panel and
`GET /api/v1/providers/cisco/setup-readiness` compose Cisco console discovery
and Cisco Ansible status into a bootstrap preview. It shows the planned
management IP, console candidate counts, prompt-readiness next action,
SSH/SCP and Ansible readiness as plan-only, backup/report placeholders, and
disabled dangerous actions. It does not expose an apply button, open config
mode, enable SSH/SCP, back up running-config, save config, reload, erase, copy,
or change VLANs, interfaces, users, or passwords.

`POST /api/v1/providers/cisco-console/prompt-readiness` is a separate
newline-only console check for the setup workflow. It opens the selected
console path only in explicit `PROVIDER_MODE=local-readonly` mode with lab
read-only acknowledgements, sends newline, reads and redacts the prompt state,
and does not run show commands or configuration commands.

`GET /api/v1/providers/cisco/setup-wizard-plan` is preview-only. It reports the
latest cached prompt-readiness state when available, explains why initial setup
wizard handling is blocked, shows future guarded bootstrap planning steps, and
keeps answer-wizard, configuration, save, reload, erase/copy, SSH/SCP,
running-config backup, and real apply actions disabled.

`GET /api/v1/providers/cisco/bootstrap-requirements` validates the preview-only
inputs needed before any future guarded bootstrap design: management IP,
subnet/prefix, gateway, management VLAN/interface strategy, hostname,
domain/DNS, local admin username presence, SSH/SCP policy, save behavior, and
explicit confirmation requirements. `PUT` to the same endpoint stores
non-secret local planning values under
`.local/cisco/bootstrap-requirements.json`, which is ignored by Git. The
workflow returns blockers/warnings only and does not generate commands, answer
setup prompts, enable SSH/SCP, save configuration, or apply anything.

`GET /api/v1/providers/cisco/console-bootstrap/plan` builds the guarded
Cisco-only console bootstrap preview for this lab target:
`192.168.1.220/24` (`255.255.255.0`). It distinguishes setup-wizard,
direct exec/config-mode, and unsupported prompt flows, shows redacted preview
commands, and keeps destructive reset/wipe actions separate and disabled.
`POST /api/v1/providers/cisco/console-bootstrap/apply` is blocked by default
and records a redacted blocked result unless all backend gates pass, including
the exact confirmation phrase
`APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.220`. The current implementation is a
guarded scaffold and does not perform serial writes.

See `app/docs/cisco-real-lab-bootstrap-runbook.md` for the safe local-lab-readwrite
operator flow, required gates, blocked-result meanings, and evidence handling.

For an isolated local lab, optional settings live in `.env.local.real-lab` at
the repository root. Do not commit that file. Create it with:

```bash
./scripts/setup-real-lab-env.sh
```

Set `PROVIDER_MODE=local-readonly` only when manually running explicit
read-only probes and require `LAB_CLOSED_LOOP_ACK=YES` and
`LAB_READONLY_ACK=YES`. iLO probes use GET-only Redfish calls with short
timeouts and redacted responses. Cisco prompt readiness opens the selected
console only after a button click and sends newline only. Cisco console probes
open the selected console only after a button click or manual smoke command,
then send newline and safe `show` commands when already at an exec prompt.
Cisco Ansible probes check SSH, parse a generated temporary inventory, and run
only fixed safe `show` commands. ESXi probes use HTTPS GET and TCP reachability
checks only.

Optional manual smoke:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

iLO-only manual smoke:

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

The backend loads local provider values from `.env.local.real-lab`, but ignores
`PROVIDER_MODE` from that file; the running app defaults to
`local-lab-readwrite`, while test targets set `PROVIDER_MODE=mock` explicitly.
Plain `make provider-smoke` runs in mock mode and skips probes. With explicit
`PROVIDER_MODE=local-readonly`, the smoke command skips missing
hardware/configuration and planned but not configured ESXi/Cisco management
targets gracefully, must not print passwords, and writes sanitized reports under
ignored `artifacts/real-lab/`. `LAB_CLOSED_LOOP_ACK=YES` and
`LAB_READONLY_ACK=YES` are required for real read-only probes. Set
`PROVIDER_SMOKE_PROVIDERS=ilo-redfish` to run only the iLO GET-only Redfish
smoke without Cisco or ESXi probes.

`PROVIDER_MODE=local-lab-readwrite` is separate from mock and local-readonly.
It requires `LAB_ENVIRONMENT=isolated-real-lab`,
`LAB_ACKNOWLEDGE_REAL_HARDWARE=true`,
`LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true`,
`LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true`, and
`LAB_ACKNOWLEDGE_LAB_ONLY=true` in `.env.local.real-lab`. Allowlisted lab
workflow categories can run only through explicit workflow steps. Power,
firmware update, and factory reset categories remain blocked unless their
specific `LAB_ALLOW_*` flags are enabled.

The firmware compliance gate runs before major configuration workflows. It
loads the baseline from `config/firmware-baselines/real-lab.yml`, collects
available iLO/Cisco/NetApp firmware and OS evidence, scans local media metadata
from `artifacts/Media` and `MEDIA_INVENTORY_DIRS`, and writes redacted reports
under `artifacts/codex-runs/`. It does not upload, flash, reboot for firmware,
or update firmware.

```bash
make provider-lab-firmware-inventory
make provider-lab-firmware-compliance
make provider-lab-firmware-waiver-check
```

When the gate is blocked, Cisco bootstrap/apply, HPE RAID apply/reset, ESXi
boot workflow actions, NetApp setup workflow previews, and full rebuild
execution surface the firmware blocker before continuing. A local waiver can be
supplied with `FIRMWARE_WAIVER_CONFIRM=WAIVE FIRMWARE COMPLIANCE`,
`FIRMWARE_WAIVER_REASON`, `FIRMWARE_WAIVER_EXPIRES`, and
`FIRMWARE_WAIVER_SCOPE`, or by writing the same fields to the ignored local
artifact `artifacts/codex-runs/firmware-waiver.json`. Active waivers are
recorded in `artifacts/codex-runs/firmware-waiver-report.md` and shown on the
Lab Builder Firmware Compliance stage.

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

The Provider Status iLO section includes an HPE Storage / RAID setup panel for
cached Smart Array inventory, desired RAID intent, and current-vs-planned ESXi
layout impact. It shows RAID apply availability and last real apply state;
destructive execution still runs through the explicit terminal target above.

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

Toolchain readiness checks local package and CLI availability for Cisco,
HPE/iLO, ESXi/vSphere, NetApp, and firmware planning without contacting real
devices:

```bash
make provider-lab-toolchain-check
```

The NetApp-only readiness command writes `netapp-readiness-*` artifacts under
the same ignored directory and never contacts ONTAP, SP, console, SSH, storage,
upgrade, reboot, wipe, or apply endpoints.

## Safety Defaults

- Runtime app: `PROVIDER_MODE=local-lab-readwrite`
- Automated tests: `PROVIDER_MODE=mock`
- No plaintext secrets are stored
- Provider credential records are references only
- Real provider adapters must require explicit configuration
- Planning and approval are separate from execution
- Production-like workflows keep the approval gate

See [docs/security.md](docs/security.md) and
[docs/provider-adapters.md](docs/provider-adapters.md).
# Standalone Windows kit

The `/simple-steps` Windows kit review follows firmware assessment and approved
updates through standalone ESXi and Windows OVF/OVA verification. See
[scope and migration decisions](docs/standalone-windows-kit.md) for required,
conditional and deferred capabilities. This review does not yet enforce backend
stage gates; unverified stages remain unverified. No hardware writes are automatic.

## Guided workspace

Start at `/setup/guide` to choose physical hardware, set rack positions and save the
layout. Continue to `/setup/connect` for per-device initial management access.
`/simple` is the read-only My Rack view; `/equipment` is its checklist view.
My Rack has one setup action, Continue setup. Selecting equipment shows saved
addresses and device-scoped cached iLO connection status without starting probes.
Detected firmware and BIOS versions use device-scoped iLO readings. Unknown
values, including per-server ESXi versions not yet collected, remain unavailable.
Editing and rack plan file actions remain in setup, not My Rack.
The main navigation has only My Rack and Setup. Setup proceeds through equipment,
network settings, connections, firmware, ESXi, and Windows. Run history is a
secondary setup destination for jobs and failures across all kits; it is not a
readiness gate. Old Equipment and Activity URLs redirect to My Rack and run history.
The shared workbench theme loads after legacy styles to align forms and review tools.
Server/iLO forms use workspace-width container queries so nested setup panels
stack before their fixed columns overflow. Responsive checks cover the standalone
server and embedded setup pages at 1024, 768, and 390 pixels without hardware writes.
NTP and SNMP dependent fields and list controls are disabled when their service
is off, retaining entered values for re-enabling. Network settings subnet changes
preserve explicit equipment addresses instead of applying last-octet offsets;
the gateway must be entered explicitly.
When a saved profile's subnet is edited while retaining its inherited topology,
the backend switches it to a custom address plan. Custom plans do not generate or
require template offsets. Explicit addresses still undergo subnet and duplicate
validation; they are not silently moved or cleared.
On a subnet transition, unchanged planned equipment addresses outside the new
network are retired from the active plan and retained in the previous revision.
Newly edited addresses still receive full validation. Bootstrap addresses,
device connection records, and submitted shared service settings are preserved.
Shared network settings no longer duplicate server onboarding; connections are
entered in the next setup step. ESXi/Windows prerequisites are collapsible, while
readiness warnings remain visible. Run history and inventory status polling pause
when the document is hidden, resume on return, and prevent overlapping refreshes.
Firmware setup now reads only the active saved rack: HPE servers, Cisco switches,
and NetApp storage are included only when present. ESXi and vCenter are installation
steps, not firmware entries. HPE uses an expandable SPP component-assessment group.
HPE checks run against the selected server and selected SPP. iLO, System ROM,
controllers, drives and network adapters use exact hardware/package evidence;
unmatched components remain unassessed. No global scan is launched. See
[SPP assessment](docs/spp-assessment.md) for discovery and matching rules.
Hardware alerts now identify the bay, reported reason and next action, independently
of firmware matching. Acknowledgements are tied to the exact reading and recorded
without clearing health faults. Review upgrades opens an audited, target-specific
HPE SUM handoff. Automatic SPP installation remains unavailable; this is not a
one-click firmware executor. Inspect/diagnose drives first, then vendor-approved
firmware updates, then RAID creation and ESXi installation.
Both use the same profile-scoped rack plan and browser draft. Save in the copy
window commits the draft to the backend after saving the file copy.
Passwords are not included in rack drafts.

Rack editing uses an image palette instead of an equipment dropdown. Drag an image
onto a rack unit to place it, drag a chassis to move it, or drop it into the removal
area (confirmation required). Drops snap the chassis top to the chosen unit and
relocate conflicting equipment into free contiguous space, searching downward first
and then from the top. Unaffected equipment and side-mounted PDUs stay in place.
If a displaced chassis cannot fit, the entire placement is rejected without changing
the rack. Out-of-bounds drops remain invalid. Direct numeric edits still validate
overlap instead of rearranging the rack while typing. Click/tap an image then a slot, or use
Move equipment then a slot, for keyboard/touch placement. Removal retains saved
connection records. Saving remains an explicit action.

The hardware picker shows only the new illustrated hardware catalog. The legacy
"Saved equipment outside this rack" section has been removed; this does not delete
inventory records, saved connections, or equipment already placed in a rack.

Reducing rack height shifts upper equipment downward in order, closing gaps only
as needed. Rack and side mounts are fitted independently. Finish editing the height
or press Enter to apply it; insufficient capacity leaves the size and layout intact.
Increasing the height keeps equipment positions unchanged. Saving a copy persists
the resized layout and existing device identities together.

Rack plans have two bottom-of-page actions: **Save a copy** and **Load plan**,
alongside the next setup step. The Save
button in the copy window saves a named `.rack-plan.json` file and the active kit.
The redundant Reload and Save rack plan toolbar buttons have been removed.
Loading asks before replacing the current draft and does not write to the server
until the next save.

The default save destination is a native folder/filename picker when supported.
Cancelling it does not save a file or change the server. A file-write error also
leaves the active kit untouched. If the subsequent server save fails, the window
reports that the copy exists but the active kit was not saved, and keeps the draft.
The explicit Browser download location option uses browser download preferences;
the app cannot choose a folder on browsers without a file picker. Capability:
[showSaveFilePicker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker).

Portable copies contain hardware models, positions, mounts, port counts and drive
occupancy, but no connection IDs, addresses, credentials, or execution evidence.
Loading preserves a connection only for an exact equipment ID/kind already in the
current rack; other equipment gets a new connection record when saved. File format
version 1 is validated, including layout limits, with a 1 MB input limit.

The remaining setup screens are `/setup/check-firmware`, `/setup/prepare-esxi` and
`/setup/install-windows`. Connect equipment now includes Connection and Drives &
RAID tabs. One drive table assigns the two-drive OS mirror, separate storage RAID
and an optional dedicated hot spare together. Health warnings are grouped into
an expandable summary. Empty/unidentified bays cannot be assigned to RAID.
Prepare ESXi contains only host settings, installer actions and management checks;
ESXi-only saves preserve existing iLO and shared network settings. The legacy
kit-wide ESXi address editor is disabled for multi-server kits rather than
presented as a per-server configuration.
Gen10 SR controllers can use separately confirmed, device-scoped deletion and
creation through HPE pending settings; unsupported controllers use attended SSA.
Advanced storage recovery also offers a separately confirmed controller factory
reset for this same supported API. See [storage reset](docs/storage-reset.md) for
its additional policy gate and current recovery limitations.
Read-only Ansible/SSA diagnostics can be enrolled separately; see
[maintenance SSA setup](docs/maintenance-ssa.md). This does not provide a boot ISO
or execute repairs.
Writes remain disabled in read-only/mock mode and require the explicit destructive
gate, fresh preflight and confirmations. No reboot or secure erase is automatic. A readback
must match the two saved bays before the boot mirror is shown as verified. See
[disk preparation](docs/disk-preparation.md). ESXi installer actions expand on demand;
Windows deployment controls open immediately. These pages are not a new automation engine: overall verified completion and
cross-stage enforcement are not yet connected to this overview. Visiting a step
does not complete it or execute a hardware action. Non-server connection flows
link to existing settings; UPS/PDU automation is not implemented here.

`/run-center` now shows read-only Activity (requests, workflow runs and latest server
inventory jobs across all kits). Original execution controls remain at `/run-tools`.
Settings and existing tools share the same top navigation. No dependencies or
installation steps were added for this UI redesign.

Frontend regression coverage: `npm run test:e2e -- tests/setup-journey.spec.ts
tests/rack-planner.spec.ts tests/lab-defaults.spec.ts tests/inventory-workflow.spec.ts`.

Storage recovery keeps shutdown, controller-reset staging and power-on as separate
confirmations. After a reset is staged, use **Start server and verify RAID** to
review and approve the next boot. HPE can report a pending FactoryReset without a
LogicalDrives list; this is a pending action, never evidence that deletion has
completed. Applied storage readback must still provide the actual logical-drive
list. Do not resubmit a staged reset just because the server remains off.

If a post-boot, target-matched controller response explicitly rejects an action-only
reset for missing `LogicalDrives`, a fresh reset preview includes `LogicalDrives: []`.
This corrected request still requires approval, no pending changes and normal safety
checks. It is not automatically retried. A confirmed intervening app-controlled boot
and a fresh On state permit a new shutdown cycle; duplicate shutdown requests within
the same cycle remain blocked.

Physical-disk erasure has a separate review, enablement, typed approval and per-drive
verification flow in Connect equipment. It does not run during RAID deletion and is
disabled by default. See [disk sanitization](docs/disk-sanitization.md) for supported
hardware scope, method enrollment, long-running status checks and historical reports.

The Prepare ESXi installer uses one approval for attaching its built ISO, setting
one-time boot and starting the server. Runs share the device-operation lock with
other guarded workflows; an interrupted send is reconciled instead of resent.
Resume must match the original iLO endpoint and hardware identity, and the boot
mirror is read again before restart. Status checks may perform approved media
cleanup, so they are not entirely read-only. An answering ESXi API is displayed
as **verification pending**, not proof of the installed disk or root credentials.
Authenticated post-install verification and VM datastore provisioning are not
implemented by this installer yet.
