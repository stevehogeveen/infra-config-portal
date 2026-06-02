# Task 002: Frontend VM Request Flow

## Goal

Improve the React VM request user flow in one narrow, testable step.

## Constraints

- Keep the UI pointed at mocked backend behavior.
- Do not add real infrastructure endpoints, credentials, IPs, hostnames,
  tokens, or secrets.
- Do not bypass lifecycle approval or planning stages in the UI.
- Keep the design utilitarian and workflow-focused.

## Expected Work

- Inspect `app/frontend/src/` and the backend API schemas before editing.
- Choose one small frontend improvement for request creation, submission,
  approval, planning, execution, status display, or audit visibility.
- Keep API calls aligned with existing backend routes.
- Add tests only if a frontend test framework is already present; otherwise
  document the test gap and rely on the configured build/type check.
- Update docs if user-facing workflow behavior changes.

## Verification

Run:

```bash
make test
```

If no frontend test runner is configured, run the frontend build/type check and
document that limitation.

## Completion

End with files changed, UI behavior changed, checks run, limitations, and the
next recommended task.
