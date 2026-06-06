# Cisco Real-Lab Console Bootstrap Runbook

Target for this run: `192.168.1.204/24` (`255.255.255.0`).

Default behavior is safe. `PROVIDER_MODE=mock` performs no real console apply.
Keep `CISCO_MGMT_CONFIGURED=false` until console bootstrap has configured
management networking and SSH is intentionally enabled by a guarded workflow.
Cisco first contact/bootstrap is still console. Ansible starts only after
management SSH is configured at `192.168.1.204`, and is then used for show
commands, backup, validation, drift checks, and future repeatable config.

## Backend Startup Modes

Mock mode is the normal test and development default:

```bash
PROVIDER_MODE=mock make test
```

Local read-only mode may be used for explicit console discovery and prompt
readiness only:

```bash
PROVIDER_MODE=local-readonly \
LAB_CLOSED_LOOP_ACK=YES \
LAB_READONLY_ACK=YES \
CISCO_CONSOLE_PORT=/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 \
make app-restart
```

Prompt readiness remains newline-only. If the console is slow or quiet, tune
only the bounded read behavior:

```bash
CISCO_CONSOLE_PROMPT_SETTLE_SECONDS=0.5
CISCO_CONSOLE_PROMPT_READ_WINDOW_SECONDS=1.0
CISCO_CONSOLE_PROMPT_MAX_BYTES=8192
```

Guarded apply remains disabled unless the apply-specific gates are also set.
Do not set apply gates for discovery or prompt-readiness checks.

## Read-Only Smoke

Use read-only mode only on an isolated lab host with the Cisco switch connected
by console:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

Read-only Cisco prompt readiness sends newline only. It does not answer setup
wizard prompts, run show commands, enter configuration mode, save config,
reload, copy, erase, or print secrets.

## Console Adapter Detection

Check the host sees the USB serial adapter before running prompt readiness:

```bash
ls -l /dev/serial/by-id/ 2>/dev/null || true
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
id
groups
```

Prefer a stable `/dev/serial/by-id/...` path over `/dev/ttyUSB0` whenever
available. Example:

```bash
CISCO_CONSOLE_PORT=/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0
```

The backend user should be in `dialout`. After adding dialout membership, log
out/in or restart the backend shell/session so group membership is refreshed.

If `/api/v1/providers/status` returns unexpected output or JSON parsing errors,
verify which backend port is serving the app:

```bash
for p in 8000 8001 8002 8003; do
  echo "=== port $p ==="
  curl -i -sS "http://127.0.0.1:$p/health" | head -20 || true
  echo
done
```

If local dev servers are stale, inspect before stopping anything:

```bash
make app-status
ls -l .local/run/ .local/log/ 2>/dev/null || true
```

Use `make app-restart` only for app-owned backend/frontend processes. To avoid
touching another process on the default ports, start this app on alternate local
ports:

```bash
BACKEND_PORT=8002 FRONTEND_PORT=5174 make app-restart
```

Discovery meanings:

- No candidates: connect the USB serial adapter to this machine, connect the
  console cable to the Cisco console port, then refresh Provider Status.
- Stable `/dev/serial/by-id/...` candidate: use it as `CISCO_CONSOLE_PORT`.
- Fallback `/dev/ttyUSB*` or `/dev/ttyACM*` only: prefer stable by-id if it
  appears after reconnecting the adapter; otherwise select the intended
  fallback path explicitly.
- Configured path missing: reconnect the adapter or update
  `CISCO_CONSOLE_PORT`.
- Path not readable/writable: check `dialout` membership and device
  permissions, then restart the backend shell/session.

## Serial Port Opens But No Prompt Text Is Captured

If Prompt Readiness opens the configured serial port but reports
`prompt_state=unknown` with no captured text, keep the workflow blocked. Do not
run show commands, do not type configuration commands, and do not answer setup
wizard prompts yet.

Host-side checks:

```bash
ls -l /dev/serial/by-id/ 2>/dev/null || true
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
sudo lsof /dev/ttyUSB0 || true
sudo fuser -v /dev/ttyUSB0 || true
picocom -b 9600 /dev/ttyUSB0
picocom -b 115200 /dev/ttyUSB0
```

Exit `picocom` with `Ctrl+A`, then `Ctrl+X`.

When observing manually, press Enter only. Do not paste commands, do not answer
prompts, and do not save raw terminal transcripts. Record only sanitized facts:
adapter path, baud tried, whether text appeared, prompt classification, and
whether any other process owned the serial port.

Manual console troubleshooting:

- Confirm the RJ45/console cable is connected to the Cisco console port, not
  an Ethernet data port.
- Confirm the switch is powered on and booted far enough for console access.
- Press Enter a few times in a manual console session.
- Check no other process owns `/dev/ttyUSB0` with `lsof` or `fuser`.
- Try baud `9600` first, then `115200` if needed.
- Prefer the stable `/dev/serial/by-id/...` path for `CISCO_CONSOLE_PORT`.
- Report only the prompt type, not passwords, usernames, secrets, or raw config.

Expected prompt types are setup wizard, `Switch>`, `Switch#`, `Username:`,
`Password:`, or no output.

Prompt classifications used by the app:

- `setup-wizard`: stop; do not answer yes/no prompts.
- `login-required`: stop; do not send usernames or passwords.
- `exec`: readiness evidence only; prompt-readiness still does not run show
  commands and reports `safe_show_commands_allowed=false`.
- `config-mode`: stop; get human review before further interaction.
- `unknown`: keep blocked until manual observation explains the prompt.
- `unknown-no-output`: keep blocked; re-check adapter ownership, cable, power,
  and baud `9600` then `115200`.

If the app reports `unknown-no-output`, keep bootstrap apply blocked and use
the manual checks above before changing baud or cabling.

## Operator Flow

1. Open `/providers`.
2. Confirm Cisco Setup Readiness shows target `192.168.1.204/24`.
3. Confirm `Management Configured` is `false`.
4. Review console discovery and select one effective console path.
5. Run Prompt Readiness only when `PROVIDER_MODE=local-readonly`,
   `LAB_CLOSED_LOOP_ACK=YES`, and `LAB_READONLY_ACK=YES` are set.
6. Review setup wizard planning. It uses cached prompt readiness only.
7. Fill Bootstrap Requirements with non-secret planning values.
8. Review Console Bootstrap Plan and redacted command preview.
9. Do not apply unless every backend gate passes and the operator enters:

```text
APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.204
```

## Guarded Apply Gates

Backend apply must block unless all of these are true:

- `PROVIDER_MODE=local-readonly`
- `CISCO_CONSOLE_APPLY_ENABLED=true`
- `LAB_APPLY_ACK=YES`
- `LAB_TARGET_ACK=192.168.1.204`
- exact confirmation phrase matches
- selected console path is ready
- prompt readiness is recent
- prompt state is `exec` or `setup-wizard`
- bootstrap requirements are complete
- planned IP is `192.168.1.204`
- planned prefix is `/24`

The current apply endpoint is a scaffold and records no serial writes. A blocked
result means no console commands were sent.

## Success And Evidence

Success for the scaffold means the plan is visible, blockers explain missing
gates, and apply attempts return redacted summaries with
`serial_writes_attempted=false`.

Collect sanitized evidence only:

- screenshots of `/providers`
- redacted API summaries
- sanitized smoke reports under ignored artifact paths
- prompt classification, checked time, baud, adapter path, blocker summaries,
  and placeholder artifact metadata

Do not collect raw running-config, passwords, tokens, cookies, authorization
headers, raw console transcripts, or local real-lab env files.

## Explicit Warnings

Destructive wipe/reset is a separate future workflow. Do not run or hide these
inside bootstrap:

- `write erase`
- `erase startup-config`
- `delete flash:*config*`
- `reload`
- `copy`
- wipe/reset commands

No config apply is allowed unless exact confirmation and environment gates are
present. No secrets belong in logs, forms, reports, screenshots, or commits.
