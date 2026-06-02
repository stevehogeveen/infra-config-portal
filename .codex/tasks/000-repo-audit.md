# Task 000: Repo Audit

## Goal

Inspect the repository and produce a concise audit that makes the next Codex
exec tasks easier to run safely.

## Constraints

- Do not implement the full infrastructure portal.
- Do not make real provider, infrastructure, storage, switch, OVF, or
  source-of-truth API calls.
- Do not add credentials, real IPs, real hostnames, tokens, or secrets.
- Do not use `--yolo` or `danger-full-access`.
- Keep providers mocked and safe by default.

## Expected Work

- Inspect project layout, backend, frontend, docs, tests, Docker Compose, and
  provider adapter boundaries.
- Identify the highest-risk gaps for the MVP.
- Confirm which local test and quality commands exist.
- Make no code changes unless a very small documentation correction is needed
  to keep the automation workflow accurate.

## Verification

Run the available tests and checks that are already configured. If a command
cannot run locally, document the exact reason.

## Completion

End with:

- Files changed, if any.
- Tests/checks run and their results.
- Top risks.
- The next three recommended task files.
