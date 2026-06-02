# Task 004: Tests And Quality Gates

## Goal

Improve the repository's local test and quality gate workflow in one narrow
step.

## Constraints

- Do not add real provider calls.
- Do not add credentials, real IPs, hostnames, tokens, or secrets.
- Do not introduce heavyweight tooling unless it is clearly justified and easy
  to run locally.
- Keep mocked providers as the default test target.

## Expected Work

- Inspect backend pytest setup, frontend package scripts, Makefiles, and docs.
- Identify one focused improvement to make `make test`, `make lint`, or related
  quality checks more repeatable.
- Add or update tests only where needed.
- Document any checks that cannot run in a clean local checkout.

## Verification

Run:

```bash
make test
make lint
```

Document exact failures or missing tools.

## Completion

End with files changed, command behavior changed, tests/checks run, limitations,
and the next recommended task.
