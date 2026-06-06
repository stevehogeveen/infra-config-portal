# UX Design Reference Notes

## Sources Checked

- W3C WCAG 2.2 Quick Reference for perceivable status, focus visibility, labels, and non-color-only cues.
- Nielsen Norman Group progressive disclosure guidance.
- Nielsen Norman Group status tracker/progress update guidance.
- GOV.UK summary list pattern for readable key/value summaries.

## Practical Choices For This App

- Lead with the user's current task, not the system architecture.
- Present one overall state, current phase, next action, and top blocker before any provider detail.
- Use a staged status tracker for the build journey so progress and waiting states are visible.
- Keep status labels textual and short; do not rely on color alone.
- Make each stage card answer four questions: status, meaning, next action, and one useful result.
- Hide raw evidence behind explicit `View details` / `Advanced diagnostics` sections.
- Treat expected missing configuration as neutral or calm, not as an error.
- Keep buttons specific: "Refresh Status", "Review Cisco Details", "Run Build Verification".
- Use semantic headings and preserve keyboard-focus visibility.
- Keep dense evidence available for power users without making it the default page.
