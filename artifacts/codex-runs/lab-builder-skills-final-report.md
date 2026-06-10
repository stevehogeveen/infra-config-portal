# Lab Builder Skills Final Report

## Summary

Created reusable project-specific Codex skills under `.codex/skills/` for Lab
Builder runtime state, operator UX, hardware-run sequencing, report
remediation, and toolchain readiness.

## Files Created

- `.codex/skills/lab-builder-real-runtime/SKILL.md`
- `.codex/skills/lab-builder-ux/SKILL.md`
- `.codex/skills/lab-builder-hardware-run/SKILL.md`
- `.codex/skills/lab-builder-report-remediation/SKILL.md`
- `.codex/skills/lab-builder-toolchain/SKILL.md`

## Files Updated

- `.codex/README.md`
- `AGENTS.md`

## Safety Notes

- No secrets were printed or added.
- No hardware workflows were run.
- No provider calls were made.
- The skills preserve mock-first defaults and require explicit real-lab gates
  for real hardware workflows.

## Validation

- Passed: `git diff --check -- AGENTS.md .codex/README.md .codex/skills/lab-builder-real-runtime/SKILL.md .codex/skills/lab-builder-ux/SKILL.md .codex/skills/lab-builder-hardware-run/SKILL.md .codex/skills/lab-builder-report-remediation/SKILL.md .codex/skills/lab-builder-toolchain/SKILL.md artifacts/codex-runs/lab-builder-skills-final-report.md`
- Lint and tests were not run because this task only changed Markdown guidance
  and artifact documentation.

## Recommended Next Step

Future Codex tasks should read the smallest matching skill set from
`.codex/skills/` before editing Lab Builder runtime, UX, hardware-run,
reporting, or toolchain behavior.
