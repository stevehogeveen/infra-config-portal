# Tier 2 — in-app "make a real change" (deeper changes routed to the Claude+Codex loop)

Goal: when a request can't be satisfied by Tier 1 layout toggles (restructure a page, add/remove a real element, change behavior), the in-app bar captures it and routes it into the same Claude+Codex build loop — branch → build → verify → review → apply. NOT a silent self-edit of a live hardware-control app.

Sequence: build AFTER Tier 1 is working.

MUST first: check `reuse-ledger.md`. Reuse the Tier-1 intent bar, the mailbox channel, and the existing verify harness — don't build a second request system.

## Flow
1. Intent bar detects (or the user selects "make a real change") a non-layout ask.
2. It captures a structured change request: `{ page, target (element/region id), request, currentLayout, screenshot }` and writes it to `app/docs/change-requests/<timestamp>.md` (+ the screenshot into `agent-shots/`).
3. The app shows the user honest status: queued → building → ready to apply → applied (or needs review). Latency is minutes, not instant — say so.
4. Codex picks up the request like any mailbox item, implements on a branch, fast-verify green; Claude reviews; it applies after the gate.
5. Result posted back; the in-app status updates.

## Hard boundary (non-negotiable)
- Tier 2 restructures UI/frontend only. It can NEVER modify the safety machinery, workflow-action code, or fire RAID/factory/rebuild — and every Tier-2 change goes through branch + fast-verify + review before it reaches the live app. No auto-apply to the running control system without the gate.
- The change-request capture writes NO code and touches NO hardware; it only records intent for the loop.

## Done =
- A non-layout request from the bar produces a structured change-request the loop can act on, with honest in-app status.
- Zero path from the bar to code-apply that skips branch + verify + review.
- Reversible capture; the build itself follows the normal green-gated loop.
