# Lab Builder Vertical Slice — Unified Engine and the Build Journey

Status: proposed (CXO brief for Codex)
Depends on: `docs/product/LAB_BUILDER_SIMPLICITY_CONTRACT.md`, Operator Home (PR #2)

## Goal

Move Lab Builder from an *inspector* (shows state, runs per-device checks) to a *builder*
(press one button, it builds the lab in dependency order and hands back a report).

This slice adds the shared workflow engine and the Build to Run to Complete journey that
Operator Home's "next safe action" should lead into. Every new surface must pass the
Simplicity Contract — this brief does not get to reintroduce the mess Operator Home removed.

## Governing rule

Everything below is subject to `LAB_BUILDER_SIMPLICITY_CONTRACT.md`:
four-question budget, one primary action, three tiers (Operator / Details / Advanced),
one fact / one owner / one display location, operator vocabulary, replace-don't-add,
five-second test. If a screen here cannot pass those, it is not done.

## Build

### 1. Unified workflow engine (the backbone)

Do not let each device page keep inventing its own process. Introduce one engine that every
provider plugs into.

Every step uses the same status lifecycle:

```
Not Started -> Preflight -> Ready -> Running -> Waiting -> Succeeded
                                             \-> Warning
                                             \-> Failed
                                             \-> Skipped
```

Every provider returns the same result structure:

```
Status            (one of the lifecycle states)
Summary           (short machine-facing summary)
OperatorMessage   (plain-language, contract vocabulary only)
TechnicalDetails  (Advanced tier only — never shown in operator mode)
SuggestedAction   (what to do next on warning/failure)
CanRetry          (bool — retry is offered only when true)
```

Every step also declares its dependencies:

```
DependsOn   (step ids / capabilities that must be Succeeded first)
Provides    (capability this step makes available, e.g. "mgmt-network", "datastore")
```

Engine responsibilities:

- Topologically sort steps from `DependsOn`/`Provides` into the ordered Build Plan.
  The operator sees a straight sequence; the engine computed it from the graph.
- A step whose prerequisites are unmet is `Blocked` and names the specific blocking
  step/capability in operator language ("Blocked by: shared storage not ready") — never
  an env var, provider name, or payload.
- Support a mid-build `Waiting` pause on an external/physical precondition
  (e.g. "waiting on: controllers powered on") and resume without restarting completed steps.
- Retrying a step re-evaluates downstream readiness for everything that `DependsOn` it.
- Reject unstartable work: a `Blocked` step cannot be started.

Keep the dependency set declared and fixed per kit. No user-editable graph, no
orchestration studio. Boring on purpose.

### 2. Build Plan screen (Operator tier)

- The ordered steps as a single hallway, each with a plain-language description.
- Blockers shown *before* execution, each naming its cause and, where possible, linking to
  the item that resolves it.
- One rationale line where order surprises a human ("Storage must be ready before the
  compute host can use it").
- Exactly one primary action: `Start Build`. Everything else is secondary/disclosure.

### 3. Run Console (Operator tier)

Show only:

- overall progress
- current step ("Step 2 of 7")
- elapsed time
- one plain-language status line (the current step's `OperatorMessage`)
- one expandable technical log (Advanced tier)

Not six log panels. One log, collapsed by default. Raw provider output, payloads, and
per-provider consoles live behind the single Advanced expander.

### 4. Completion Report (Operator tier)

- Counts: completed, warnings, failed (each shown once — one owner).
- For each failure: what happened, what was changed, what is safe, what to do next
  (`SuggestedAction`), and a `Retry` control that appears only when `CanRetry` is true.
- Exportable run summary (handoff artifact).

### 5. Advanced drawer

One entry, consistent with Operator Home. Holds: dependency graph, provider states, raw
logs, verification evidence, API payloads, audit proof, manual overrides. Nothing here may
appear in operator mode.

### 6. Preserve current device capabilities

Do not remove Cisco, NetApp, ESXi, iLO, QNAP, Windows, OVF, or VM workflows. Wrap each
existing provider action so it returns the unified result contract and declares its
dependencies. Do not redesign provider implementations except where required to satisfy the
result contract. Do not add new device types. Do not add top-level navigation.

## Tests (acceptance proof)

1. A kit moves through the full status lifecycle end to end.
2. A `Blocked` step cannot start, and the UI shows the *named* blocking step in operator
   language (assert the specific cause string, not just "blocked").
3. A `Failed` step exposes a `SuggestedAction`.
4. A successful step can be retried only when `CanRetry` is true.
5. Retrying a step re-evaluates downstream readiness (a downstream step returns to a
   not-ready state when its prerequisite is retried).
6. A mid-build `Waiting` state pauses the run and resumes without re-running completed steps.
7. Technical details (`TechnicalDetails`, raw logs, payloads) remain hidden in operator mode
   and appear only under Advanced.
8. Each count/fact on the Completion Report and Run Console renders once (one owner).

## Do not do

- No new device types.
- No new top-level navigation, tabs, or inspection surfaces.
- No user-editable dependency graph or general orchestration UI.
- No developer vocabulary (provider, runtime, payload, env mode) in operator-tier copy.
- No second log surface — one expandable log only.

## Decision

Build the unified engine and the Build to Run to Complete journey as one vertical slice,
governed by the Simplicity Contract. This is the move from inspector to builder.

## Next best task

Confirm what the existing `safe-action-runner` already provides, then implement the unified
step lifecycle, result contract, and `DependsOn`/`Provides`, followed by the Build Plan
screen. Wire it to Operator Home's next-safe-action.

## Watch for

Run Console regressing into log confetti; engine work stalling behind UI polish; blocked
messages leaking provider vocabulary; counts re-multiplying across surfaces.
