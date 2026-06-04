# Overnight Codex Runs

This worktree has a repeatable overnight runner for aggressive but safe Codex
self-improvement tasks. The runner combines
`.codex/overnight-system-prompt.md` with `.codex/overnight-queue.md`, runs
`codex exec`, captures logs, and writes a morning summary under `.codex/runs/`.

The overnight queue is intentionally greedy about app code, tests, UI cleanup,
schemas, docs, local scripts, self-healing hints, and clean commits. It remains
strict about real infrastructure: no secrets, no firmware flashing, no reboots
or power actions, no destructive device file operations, no real iLO writes, and
no hidden bypasses around safety gates.

## Manual Run

From the worktree root:

```bash
cd /home/administrator/infra-config-portal-ilo
./run-codex-overnight.sh
```

Generated files are written to `.codex/runs/`:

- `overnight-YYYYMMDD-HHMMSS.log`: full `codex exec` output.
- `overnight-YYYYMMDD-HHMMSS-final.md`: final Codex response.
- `overnight-YYYYMMDD-HHMMSS-summary.md`: paste-back morning summary.

Use smoke mode to validate the runner without starting Codex:

```bash
cd /home/administrator/infra-config-portal-ilo
CODEX_OVERNIGHT_SMOKE=1 ./run-codex-overnight.sh
```

## Schedule With `at`

Example for a one-time run tonight:

```bash
cd /home/administrator/infra-config-portal-ilo
printf 'cd /home/administrator/infra-config-portal-ilo && ./run-codex-overnight.sh\n' | at 23:30
```

Check scheduled jobs:

```bash
atq
```

Remove a scheduled job:

```bash
atrm JOB_ID
```

## Schedule With `cron`

Edit the crontab:

```bash
crontab -e
```

Example nightly run at 23:30:

```cron
30 23 * * * cd /home/administrator/infra-config-portal-ilo && ./run-codex-overnight.sh
```

Cron runs with a minimal environment. If `codex` is not on cron's `PATH`, use
the full path returned by `command -v codex` in an interactive shell.

## Safe Defaults

The runner defaults to:

```bash
CODEX_SANDBOX_MODE=workspace-write
CODEX_APPROVAL_POLICY=never
```

`danger-full-access` is not default because overnight automation must not have
broad filesystem access unless the local sandbox cannot run and the work is
isolated to app-code edits. It should never be used to touch real
infrastructure, secrets, provider credentials, firmware, power controls, or
device write paths.

Use `danger-full-access` only for isolated local app-code work:

```bash
cd /home/administrator/infra-config-portal-ilo
CODEX_SANDBOX_MODE=danger-full-access \
CODEX_DANGER_ACK=I_UNDERSTAND \
./run-codex-overnight.sh
```

Never export this globally. Set it only on the single command that needs it.

## Review Morning Reports

In the morning:

```bash
cd /home/administrator/infra-config-portal-ilo
ls -lt .codex/runs/overnight-*
sed -n '1,220p' .codex/runs/overnight-*-summary.md
git status --short --branch
git log --oneline -5
```

Review the final response and log for blocked items, failed tests, commits, and
any uncommitted changes. Do not continue manual work until `git status` is
understood.

The morning summary is suitable to paste into ChatGPT/Nova. It records the
worktree, sandbox mode, prompt and queue files, git status before and after,
recent commits, and where to find the full log/final response.

## Stop The Runner

Find a running process:

```bash
ps -ef | grep '[c]odex exec'
ps -ef | grep '[r]un-codex-overnight.sh'
```

Stop it:

```bash
kill PID
```

If it does not stop cleanly:

```bash
kill -TERM PID
```

After stopping, review `.codex/runs/`, then run:

```bash
git status --short --branch
```
