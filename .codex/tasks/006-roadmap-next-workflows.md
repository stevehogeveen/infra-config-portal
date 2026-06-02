# Task 006: Roadmap Next Workflows

## Goal

Create or refine a pragmatic roadmap for the next safe workflows after the VM
deployment MVP.

## Constraints

- Do not implement new workflows in this task.
- Do not add real provider calls.
- Do not add credentials, real IPs, hostnames, tokens, or secrets.
- Keep every future workflow mock-first with plan, approval, execution, and
  audit stages.

## Expected Work

- Inspect existing docs, models, provider boundaries, and MVP workflow.
- Propose the next workflows in dependency order.
- For each workflow, define safe mock scope, provider adapter boundaries,
  validation needs, approval points, and test expectations.
- Update docs only; avoid code changes unless needed to keep docs linked.

## Verification

Run documentation-adjacent checks if configured. If no docs checks exist, state
that no docs-specific local check is configured.

## Completion

End with files changed, roadmap decisions, checks run, limitations, and the
next recommended task.
