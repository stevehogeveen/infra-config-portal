# Cisco Real-Lab Console Bootstrap Runbook

Target for this run: `192.168.1.220/24` (`255.255.255.0`).

Default behavior is safe. `PROVIDER_MODE=mock` performs no real console apply.
Keep `CISCO_MGMT_CONFIGURED=false` until console bootstrap has configured
management networking and SSH is intentionally enabled by a guarded workflow.

## Read-Only Smoke

Use read-only mode only on an isolated lab host with the Cisco switch connected
by console:

```bash
PROVIDER_MODE=local-readonly make provider-smoke
```

Read-only Cisco prompt readiness sends newline only. It does not answer setup
wizard prompts, run show commands, enter configuration mode, save config,
reload, copy, erase, or print secrets.

## Operator Flow

1. Open `/providers`.
2. Confirm Cisco Setup Readiness shows target `192.168.1.220/24`.
3. Confirm `Management Configured` is `false`.
4. Review console discovery and select one effective console path.
5. Run Prompt Readiness only when `PROVIDER_MODE=local-readonly`,
   `LAB_CLOSED_LOOP_ACK=YES`, and `LAB_READONLY_ACK=YES` are set.
6. Review setup wizard planning. It uses cached prompt readiness only.
7. Fill Bootstrap Requirements with non-secret planning values.
8. Review Console Bootstrap Plan and redacted command preview.
9. Do not apply unless every backend gate passes and the operator enters:

```text
APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.220
```

## Guarded Apply Gates

Backend apply must block unless all of these are true:

- `PROVIDER_MODE=local-readonly`
- `CISCO_CONSOLE_APPLY_ENABLED=true`
- `LAB_APPLY_ACK=YES`
- `LAB_TARGET_ACK=192.168.1.220`
- exact confirmation phrase matches
- selected console path is ready
- prompt readiness is recent
- prompt state is `exec` or `setup-wizard`
- bootstrap requirements are complete
- planned IP is `192.168.1.220`
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
