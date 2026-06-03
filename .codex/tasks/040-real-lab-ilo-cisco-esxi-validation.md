# 040 - Real Lab iLO Cisco ESXi Validation

## Goal

Start real closed-loop lab validation for:

- HPE iLO / Redfish at `ILO_TEST_HOST`
- ESXi at `ESXI_TEST_HOST`
- Cisco switch through dynamic console discovery, then management IP `CISCO_TARGET_IP`
- Cisco Ansible provider once SSH is reachable

Use `/home/administrator/lab-builder` and `reference/lab-builder-reference.md` to learn already-solved lessons, especially around:
- console setup prompts
- restarts/reboots
- bootstrap flows
- readiness/blockers
- Run Center
- artifacts/debug bundles
- guarded execution
- retries with clear stop reasons

Do not port Lab Builder wholesale. Extract workflow lessons and safety patterns.

## Critical Safety

This is a real lab run.

Default allowed behavior:
- read-only discovery
- connectivity checks
- provider status checks
- safe show commands
- API health checks
- dry-run plans
- readiness/blocker reports
- artifact/report placeholders

Destructive/rebuild behavior is allowed only if all are true:

- `LAB_CLOSED_LOOP_ACK=YES`
- `LAB_READONLY_ACK=YES`
- `LAB_DESTRUCTIVE_ACK=REBUILD_LAB`

If destructive mode is not enabled:
- do not wipe
- do not reset
- do not reinstall
- do not change config
- do not apply switch config
- do not mount virtual media
- do not power cycle
- do not firmware upgrade
- do not write memory
- do not reload
- do not enter Cisco config mode

Even when destructive mode is enabled:
- create a plan first
- show intended target
- compare discovered state
- log `[DISCOVER]`, `[COMPARE]`, `[PLAN]`, `[DECISION]`, `[BLOCKED]`, `[APPLY]`, `[VERIFY]`
- stop on target mismatch
- never continue if the discovered device is not the intended device
- redact secrets
- save reports under `artifacts/real-lab/`
- keep generated artifacts out of Git unless they are sanitized summaries

## Local Secret Handling

Use `.env.local.real-lab` only. It is ignored by Git.

Never print or commit:

- passwords
- tokens
- authorization headers
- cookies
- private keys
- raw configs with secrets
- full unredacted running-config
- local media filenames if sensitive

Redact secrets from logs and reports.

## Phase 1 - Preflight

Inspect current repo and old Lab Builder reference.

Verify:

- app tests pass
- provider-smoke works
- provider status endpoint works
- `.env.local.real-lab` exists
- required env vars are present
- dangerous mode is clearly on/off
- Ansible availability
- serial candidates under `/dev/serial/by-id`, `/dev/ttyUSB*`, `/dev/ttyACM*`
- iLO connectivity to `ILO_TEST_HOST`
- ESXi connectivity to `ESXI_TEST_HOST`
- Cisco management IP connectivity to `CISCO_TARGET_IP`

Do not mutate anything in Phase 1.

## Phase 2 - iLO Read-Only Discovery

Use Redfish only, read-only.

Test and report:

- service root
- manager info
- system info
- chassis info if safe
- firmware/inventory summary if safe
- power state read only
- TLS behavior
- normalized errors
- timeout behavior
- redaction

Do not:

- power on/off/reset
- mount/eject virtual media
- change boot order
- change BIOS
- update firmware
- change users

Add or improve UI/API if needed so Provider Status shows the real read-only result clearly.

## Phase 3 - Cisco Console Discovery

Dynamically discover console candidates.

Test and report:

- stable `/dev/serial/by-id` candidates
- fallback `/dev/ttyUSB*` and `/dev/ttyACM*`
- permissions/read-write status
- selected/effective console path
- prompt detection if safe
- blocked states for login/setup wizard/unknown prompt

Read-only console probe may send newline and safe show commands only if already at a safe prompt.

Do not enter config mode unless destructive mode is enabled and the task is specifically doing guarded bootstrap.

## Phase 4 - Cisco Ansible Read-Only

If Cisco management IP is reachable and SSH is available, test Ansible read-only path.

Allowed:
- ansible version
- inventory parse
- ping/connectivity if safe
- facts/show commands
- show version
- show inventory
- show interfaces status
- show ip interface brief
- show vlan brief
- backup running-config only if secrets are redacted and artifact is local ignored

Do not:
- configure terminal
- write memory
- reload
- copy/erase
- VLAN/interface/user changes
- firmware upgrades

Update Provider Status and Run Center if needed to show console vs Ansible roles.

## Phase 5 - ESXi Read-Only Discovery

Use safe read-only methods only.

Allowed:
- HTTPS/API reachability
- version/build if safe
- host summary if safe
- datastore/network summary if safe
- SSH reachability if configured
- pyvmomi/govc/PowerCLI only if already available and read-only

Do not:
- reinstall
- reboot
- change network
- add/remove datastore
- create/delete VM
- deploy OVF
- power operations
- firewall/config changes

Add ESXi provider preview/status if missing.

## Phase 6 - Guarded Rebuild/Bootstrap Planning

If `LAB_DESTRUCTIVE_ACK=REBUILD_LAB`, prepare guarded plans for:

- Cisco console bootstrap to management IP `CISCO_TARGET_IP`
- enabling SSH/SCP if desired
- ESXi rebuild/config workflow preview
- iLO virtual media/boot workflow preview
- firmware upgrade workflow preview

But do not apply automatically unless the app has a clear explicit confirmation step and the target identity was verified.

If the app does not yet have strong enough confirmation UX, build the preview/plan/report only and stop.

## Phase 7 - Reports and Artifacts

Create sanitized reports under:

- `artifacts/real-lab/`

Include:

- discovered targets
- provider status
- probe results
- blockers
- readiness
- safe next actions
- redacted errors
- screenshots if available
- what was not attempted and why

Do not commit these artifacts unless they are sanitized and intentionally meant to be tracked.

## Retry Rules

Retry transient failures up to 3 times.

Examples:
- service startup race
- network timeout
- device reboot/restart prompt
- serial prompt delay

Do not retry forever.

If a device prompts for restart/reboot:
- capture the prompt
- record the required action
- do not reboot unless destructive mode and target identity are confirmed
- resume discovery after reboot only if safe

## Quality Gates

Run:

- `make provider-smoke`
- `make smoke`
- `make test`
- `make lint`
- `git diff --check`

Normal tests must not require hardware.

Hardware/manual probe failures should be reported as lab blockers, not normal test failures.

## Acceptance Criteria

- iLO, Cisco console, Cisco Ansible, and ESXi have clear provider status/readiness surfaces.
- Real read-only probes are explicit and redacted.
- Cisco console discovery is dynamic.
- Ansible is used for Cisco SSH-based automation direction.
- ESXi provider preview exists or is improved.
- Reports/artifacts summarize discoveries and blockers.
- No secrets are committed.
- No destructive action happens unless explicitly gated.
- Tests remain green.
