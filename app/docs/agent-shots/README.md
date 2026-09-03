# Agent screenshots

Codex drops app screenshots here so Claude can see the running UI and give detailed design feedback. Claude can read PNG/JPG directly but can't open Steve's browser — this is the bridge.

Flow:
1. Codex captures the app screen (the whole page, or the specific surface in question) and saves a PNG here, named `<date>-<surface>.png` — e.g. `2026-07-07-design-map.png`, `2026-07-07-device-workspace.png`, `2026-07-07-single-server-mode.png`.
2. Codex adds a line in `../agent-chat.md`: `shot: agent-shots/<file> — <what it shows / what to look at>`.
3. Claude reads the PNG and replies in `agent-chat.md` with specific, actionable change notes — what's off, where, and the fix.

Keep only the latest few per surface. Delete stale shots so this stays light.
