We are working in the ~/infra-config-portal-netapp worktree only.

Current issue:
Each time the app is restarted, it closes my Firefox web GUI/browser. This must stop. Restarting the app should never close Firefox, Chrome, or any browser. It should only stop/restart the backend and frontend dev server processes owned by this app.

Recent completed NetApp work:
- Implemented netapp-ontap provider preview.
- Implemented GET /api/v1/providers/netapp-ontap/plan-preview.
- Added frontend plan-preview display.
- Tests passed:
  - cd app && PROVIDER_MODE=mock make backend-test: 98 passed
  - cd app/frontend && npm run build: passed
  - make lint: passed
- .codex/runs/latest.md does not exist in this worktree.

Safety rules:
Do not configure ONTAP.
Do not create clusters, SVMs, LIFs, volumes, or change IPs.
Do not upgrade ONTAP.
Do not reboot/wipe/apply anything.
Do not add real ONTAP probes.
Do not expose or commit secrets.
Do not commit .env.local.real-lab, .env.local.providers, artifacts, generated reports, raw configs, passwords, tokens, or credentials.

Task:
Fix the local app restart/start/stop workflow so restarting the app never closes Firefox or any browser.

Start by inspecting:
- git status --short
- README.md
- app/README.md
- Makefile
- app/Makefile
- scripts/
- run scripts
- docker-compose files
- package.json scripts
- any shell scripts or Make targets that stop ports/processes
- any references to firefox, chrome, chromium, pkill, killall, fuser, lsof, uvicorn, vite, npm, node, port 8000, port 8001, port 5173

Find the exact command that is closing Firefox or killing too broadly.

Implementation requirements:
1. Do not kill browsers.
The scripts must never run commands that match/kill:
- firefox
- chrome
- chromium
- browser processes
- arbitrary processes connected to the frontend port

2. Replace broad process killing with narrow app-owned process cleanup.
Prefer one of these safe patterns:
- PID files written by the app start script and read by the stop script.
- Exact command matching for uvicorn backend and Vite frontend only.
- Port cleanup that verifies process command lines before killing.

3. If freeing ports is needed, only kill processes when their command line clearly belongs to this app:
- backend: uvicorn app.main:app or equivalent from this repo/app/backend
- frontend: vite/npm dev server from this repo/app/frontend
Do not kill clients connected to the port.

4. Add or update scripts so there is a clear safe workflow:
- start app
- stop app
- restart app
- status/check app
These should preserve the browser.

5. Add logging/output that clearly says what process is being stopped and why.

6. Update docs with the safe restart commands.

7. Add tests if practical.
If shell-script tests are not already present, add a lightweight check or document manual verification.

Validation:
Run these checks:
- grep -RniE 'firefox|chrome|chromium|pkill|killall|fuser|lsof|uvicorn|vite|5173|8000|8001' Makefile app/Makefile scripts app package.json docker-compose*.yml app/docker-compose*.yml || true
- cd app && PROVIDER_MODE=mock make backend-test
- cd app/frontend && npm run build
- make lint

Manual verification to summarize:
- Restart command no longer kills browser processes.
- Browser can stay open on the app URL while backend/frontend restart.
- Only app-owned backend/frontend server processes are stopped.

Stop conditions:
- If unrelated uncommitted work exists, do not overwrite it.
- If the current scripts are not responsible for closing Firefox, identify the likely external command and document the safest app-side change.
- If there are multiple restart paths, fix the documented/default one first and list any remaining risky paths.

Final response must include:
- root cause found
- files changed
- exact safe start/stop/restart commands
- tests/checks run and results
- whether Firefox/browser killing is eliminated
- recommended next step
