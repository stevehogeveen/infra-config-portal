# Task Template

Use this shape for future Codex exec task prompts:

## Goal

Describe one small, concrete outcome.

## Constraints

- Keep work inside the repository.
- Do not ask questions unless blocked.
- Keep providers mocked and safe by default.
- Do not add real credentials, IPs, hostnames, tokens, or secrets.
- Do not make real infrastructure or storage API calls.
- Do not use `--yolo` or sandbox bypass flags.
- Do not use `danger-full-access` by default; it is allowed only through the
  repository wrapper scripts with `CODEX_DANGER_ACK=I_UNDERSTAND`.

## Expected Work

- Inspect relevant files before editing.
- Make narrow changes.
- Add or update tests when behavior changes.
- Update docs when workflows, commands, or safety assumptions change.

## Verification

List the specific local commands Codex should run.

For tasks that change visible frontend UI, include local screenshot validation
when practical. Screenshots should cover the changed page or section and at
least one relevant validation, empty, blocked, or error state when applicable.
Save them only under ignored local paths such as `artifacts/screenshots/`, and
state why plus manual UI checks if screenshots are skipped.

## Completion

End with files changed, tests run, any limitations, and recommended next steps.
