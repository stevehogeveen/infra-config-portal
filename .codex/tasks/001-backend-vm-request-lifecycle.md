# Task 001: Backend VM Request Lifecycle

## Goal

Improve the backend VM deployment request lifecycle in one narrow, testable
step.

## Constraints

- Use mock providers only.
- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or external infrastructure API calls.
- Do not add credentials, real IPs, real hostnames, tokens, or secrets.
- Preserve approval gates and audit logging.
- Do not implement unrelated workflows.

## Expected Work

- Inspect `app/backend/app/services/lifecycle.py`, provider interfaces, models,
  schemas, routes, and existing backend tests.
- Choose the smallest backend lifecycle improvement that advances the MVP.
- Add or update focused tests for the changed behavior.
- Update docs if lifecycle states, API behavior, or safety assumptions change.

## Verification

Run:

```bash
make test
```

If the full command cannot run, run the most relevant backend tests directly
and document why the full command was not possible.

## Completion

End with files changed, behavior changed, tests run, limitations, and the next
recommended task.
