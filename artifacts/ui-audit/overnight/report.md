# Overnight UI Audit

Date: 2026-06-02

Target app:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8001`
- Provider mode: `mock`

Method:

- Read `reference/lab-builder-reference.md`.
- Used the existing UI audit reports before changing UI surfaces.
- Verified `/health` returned `provider_mode: mock`.
- Reused existing local mock sample requests and workflow runs.
- Attempted to capture updated screenshots under `artifacts/ui-audit/overnight/`.

Screenshot result:

- No screenshots were captured.
- `playwright` is not installed in the frontend package.
- Firefox headless with `--screenshot`, `--no-remote`, and a temporary profile hung and had to be stopped.
- No screenshot files were created or committed.

Routes intended for capture:

- `/requests`
- `/requests/cbc47d7c-38fd-4d44-b041-bccbc2be3290#artifacts`
- `/workflow-runs/796eccdd-1a53-4ade-ab87-f6ef20197baa#artifacts`
- `/audit-events`
- `/run-center`
- `/media`
- `/providers`

What changed during the overnight buildout:

- Provider Status now redacts configured iLO host/user values and clarifies Cisco discovery selection.
- Workflow runs and requests now expose mock artifact/report metadata and redacted debug/export placeholders.
- A full VM request list route provides status, owner, environment, site, search, readiness, and blocked filters.
- Audit Events now filter by request ID, workflow run ID, event type, status, link scope, and text payload.
- Media Inventory now uses redacted configured-directory labels and states the metadata-only safety boundary.

Checks run:

- `make provider-smoke`
- `make smoke`
- `make test`
- `make lint`
- `git diff --check`

Safety notes:

- All checks ran in default mock mode.
- No real infrastructure calls were made.
- No local media files, debug bundles, provider artifacts, or screenshots were generated.
- iLO local configuration presence was visible only as booleans in provider smoke output.
