# Overnight Queue: iLO Worktree

## Latest Known State

- Current local branch observed during setup: `work/ilo-flow`.
- User handoff said the iLO branch was clean and committed at `4ba19ba`,
  `Improve iLO GET-only endpoint detection`.
- Setup inspection found the worktree clean at `f618bd4`,
  `Clarify iLO web endpoint detection guidance`.
- `ILO_TEST_HOST=192.168.1.202` is configured locally in ignored
  `.env.local.real-lab`; do not print or commit that file.
- Latest read-only endpoint classification was
  `web_available_redfish_not_found`.
- `/redfish/v1/` returned `404`.
- `/redfish/v1` returned `404`.
- `/` returned `200 text/html`.
- `/xmldata?item=All` returned `404`.
- Backend was verified on alternate port `8002`.
- Frontend was verified on alternate port `5175`.

## Safety Constraints

- Keep endpoint detection GET-only.
- Keep all iLO apply, write, destructive, firmware, reboot, reset, erase, and
  power-control actions blocked.
- Do not add real iLO writes or ungated execution paths.
- Use mock tests by default.
- Use local read-only probes only when explicitly requested by a future human
  task; do not run live probes during this overnight queue.

## Required Checks After Each Safe Slice

- `python3 -m compileall app/backend/app`
- `cd app && PROVIDER_MODE=mock make backend-test`
- `cd app/frontend && PROVIDER_MODE=mock npm run build`
- `git diff --check`
- `PROVIDER_MODE=mock make lint`

## Queue

1. Capture starting state.
   - Run `git status --short --branch` and `git log -1 --oneline`.
   - Confirm no secrets or local real-lab files are staged.

2. Improve UI/readiness clarity for `web_available_redfish_not_found`.
   - Make the readiness state clearly distinguish reachable web UI from missing
     Redfish root.
   - Explain that HTTP web reachability alone does not prove supported Redfish.
   - Keep text concise and operator-focused.
   - Add or update focused tests.

3. Improve operator guidance for likely causes.
   - Wrong IP: web server may be another device.
   - Legacy iLO: older generations may not expose Redfish at `/redfish/v1`.
   - Redfish unavailable: management UI reachable but API disabled/unavailable.
   - Non-iLO web server: root page responds but iLO-specific probes do not.
   - Avoid suggesting any write action as a next step.

4. Add tests for endpoint classification and readiness text.
   - Cover `web_available_redfish_not_found`.
   - Cover root `200 text/html` with Redfish and legacy XML probes returning
     `404`.
   - Verify user-facing readiness text stays read-only and does not imply
     apply/write readiness.

5. Re-review iLO safety model.
   - Search the diff for POST, PUT, PATCH, DELETE, firmware, reboot, reset,
     power, erase, copy, write, apply, and confirmation gate changes.
   - If any unsafe behavior appears, revert only your own unsafe edits and
     write a blocked note.

6. Commit only a clean passing safe slice.
   - Suggested message: `Clarify iLO web-only readiness guidance`.
   - Commit only after all required checks pass.

7. Write the final morning summary under `.codex/runs/` and as the final Codex
   response.
