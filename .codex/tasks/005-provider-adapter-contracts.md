# Task 005: Provider Adapter Contracts

## Goal

Clarify or strengthen provider adapter contracts while keeping all provider
behavior mocked.

## Constraints

- Do not make real vSphere, ESXi, iLO, NetApp, switch, OVF, storage, AWX,
  Terraform, NetBox, Nautobot, or external infrastructure API calls.
- Do not add credentials, real IPs, real hostnames, tokens, or secrets.
- Do not implement real provider adapters in this task.
- Preserve dry-run/plan/approval/audit expectations.

## Expected Work

- Inspect `app/backend/app/providers/`, lifecycle service, tests, and
  `app/docs/provider-adapters.md`.
- Improve one narrow aspect of the adapter contract, such as typed results,
  mock behavior expectations, error handling, or contract tests.
- Keep implementation compatible with the current mock provider.
- Update docs if adapter expectations change.

## Verification

Run the relevant backend tests and `make test` if possible.

## Completion

End with files changed, contract behavior changed, tests run, limitations, and
the next recommended task.
