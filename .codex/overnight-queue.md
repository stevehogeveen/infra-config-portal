# Overnight Queue: Cisco Worktree

## Latest Known State

- Current local branch observed during setup: `work/cisco-flow`.
- User handoff said the Cisco worktree had 9 modified files and no commit.
- Setup inspection found commit `0527dcb`,
  `Improve Cisco console prompt readiness handling`, already present.
- Setup inspection found 6 currently modified files:
  - `app/backend/app/providers/cisco_console.py`
  - `app/backend/app/schemas.py`
  - `app/backend/app/services/cisco_setup_readiness.py`
  - `app/backend/tests/test_provider_status_adapters.py`
  - `app/frontend/src/App.tsx`
  - `app/frontend/src/types.ts`
- Previous checks reportedly passed before the latest local state:
  - `cd app/backend && PROVIDER_MODE=mock .venv/bin/pytest -q`, 134 passed.
  - `cd app/frontend && PROVIDER_MODE=mock npm run build`, passed.
  - `PROVIDER_MODE=mock make lint`, passed with backend ruff skipped.
- Real console prompt readiness at `9600` and `115200` captured no text.
- `safe_show_commands_allowed=false`.
- Bootstrap plan remains blocked.
- Actual serial executor was not implemented.
- Real console apply was not attempted.

## Safety Constraints

- Keep no-output readiness newline-only.
- Do not send show commands.
- Do not answer setup wizard prompts.
- Do not enter config mode.
- Do not send credentials.
- Do not write memory.
- Do not reload.
- Do not erase, copy, delete, or modify device files.
- Do not implement real apply yet.
- Keep planned management IP separate from confirmed reachable/current device
  state.
- Use mock tests by default.
- Do not run live serial probes during this overnight queue.

## Required Checks After Each Safe Slice

- `python3 -m compileall app/backend/app`
- `cd app && PROVIDER_MODE=mock make backend-test`
- `cd app/frontend && PROVIDER_MODE=mock npm run build`
- `git diff --check`
- `PROVIDER_MODE=mock make lint`

## Queue

1. Capture starting state.
   - Run `git status --short --branch` and `git log -1 --oneline`.
   - Confirm no secrets, local env files, or raw console transcripts are staged.

2. Review the current diff.
   - Check for secrets, unrelated edits, unsafe behavior, accidental real apply,
     show-command execution, credentials, config mode, write memory, reload,
     copy, erase, delete, or weakened gates.
   - If the diff is the already-requested safe slice, run all required checks.
   - If checks pass, commit the current safe slice. Use
     `Improve Cisco console prompt readiness handling` only if that exact commit
     is still missing; otherwise use a focused message for the actual current
     slice, such as `Clarify Cisco no-output readiness troubleshooting`.
   - If checks fail, do not commit. Save the failure summary.

3. Improve no-output troubleshooting display after the current safe slice is
   committed or explicitly found already committed.
   - Make no-output readiness guidance clear for operators.
   - Keep `safe_show_commands_allowed=false`.
   - Keep prompt readiness newline-only.
   - Keep bootstrap apply blocked.
   - Do not add real serial writes or command execution.
   - Add or update focused backend/frontend tests.

4. Preserve state boundaries.
   - Planned management IP is local planning data only.
   - Confirmed reachable/current device state must come only from explicit
     read-only evidence.
   - UI wording must not imply the planned IP is already configured or
     reachable.

5. Re-review Cisco safety model.
   - Search the diff for show commands, configure terminal, username/password
     handling, enable secrets, write memory, reload, copy, erase, delete,
     serial writes, apply execution, and confirmation gate changes.
   - If any unsafe behavior appears, revert only your own unsafe edits and
     write a blocked note.

6. Commit only clean passing safe slices.
   - Commit after all required checks pass.
   - Keep commits focused and separate from generated run logs.

7. Write the final morning summary under `.codex/runs/` and as the final Codex
   response.
