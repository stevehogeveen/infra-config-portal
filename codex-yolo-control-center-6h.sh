#!/usr/bin/env bash
set -u

HOURS="${HOURS:-6}"
REPO_ROOT="$(pwd)"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$REPO_ROOT/.codex/runs/yolo-control-center-$RUN_ID"
PROMPT_DIR="$RUN_DIR/prompts"
LOG_DIR="$RUN_DIR/logs"
BRANCH_NAME="work/yolo-control-center-firmware-$RUN_ID"

mkdir -p "$PROMPT_DIR" "$LOG_DIR"

echo "== YOLO Control Center Codex Run =="
echo "Repo: $REPO_ROOT"
echo "Hours: $HOURS"
echo "Branch: $BRANCH_NAME"
echo "Run dir: $RUN_DIR"
echo

if ! command -v codex >/dev/null 2>&1; then
  echo "ERROR: codex command not found."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: Run this from inside the git repo."
  exit 1
fi

git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"

cat > "$PROMPT_DIR/main.md" <<'PROMPT'
You are in codex exec YOLO mode.

Be decisive. Make the changes you believe are right.

The app has become too messy and has drifted away from the intended vision. Restore it into a simple WebUIs Control Center.

Do not ask product questions.
Do not make tiny cosmetic patches.
Do not stop after moving one button.
Do not preserve bad layout just because it exists.
You may reorganize components, simplify routes, remove confusing active UI, create adapters, reconnect backend functions, and make broad frontend changes if that is the correct move.

Primary goal:
Create a practical Control Center with this sidebar:

1. Dashboard
2. Configure
3. Run
4. Firmware
5. Results
6. Logs
7. Settings

Primary workflow:
Configure target/settings -> Run action -> View results/logs.

Firmware gets its own dedicated tab/page for:
- what firmware the app can see
- firmware validation
- firmware upgrade workflow
- firmware logs/events

Important firmware safety:
Do not automatically trigger a real firmware upgrade on page load.
Do not start destructive firmware actions without explicit UI confirmation.
Start Firmware Upgrade must require confirmation.
If backend firmware functionality exists, wire it in.
If backend support is missing, create safe TODO placeholder adapters and make the UI say backend integration is pending.
Do not make fake upgrades look real.

Required behavior:

Dashboard:
- Current target
- API/connection status if available
- IP mode
- SNMP version
- detected firmware summary
- last run status
- last firmware check/upgrade status
- quick links to Configure, Run, Firmware

Configure:
- target host/IP/range
- IP mode: IPv4, IPv6, Both
- SNMP version: SNMPv2, SNMPv3
- SNMPv2 community field
- SNMPv3 credential fields when selected
- timeout/retry fields if supported
- advanced section collapsed by default
- save/apply config
- validation errors

Run:
- current config summary
- one obvious Run button
- loading, success, error states
- latest result preview
- logs activity

Firmware:
Create a dedicated Firmware page with these sections:

1. Firmware Visibility
- detected device/model
- current firmware version
- available firmware version if supported
- build/date if supported
- bootloader/version if supported
- hardware revision if supported
- compatibility status
- last check time
- detection source if supported
- Check Firmware button

2. Firmware Upgrade
- target summary
- current firmware
- selected firmware/image/version
- compatibility check
- readiness status
- Validate Firmware button
- Start Firmware Upgrade button
- confirmation required before upgrade
- block missing fields
- block failed validation unless a clear supported override exists
- progress if supported
- states: idle, validating, ready, upgrading, success, failed

3. Firmware Events
- checks
- validations
- upgrade attempts
- success/failure
- backend errors
- timestamps

Results:
- latest run result
- latest firmware check summary
- latest firmware upgrade summary
- empty/error states

Logs:
- config saved
- run started/succeeded/failed
- firmware check started/succeeded/failed
- firmware validation started/succeeded/failed
- firmware upgrade started/succeeded/failed
- settings changed

Settings:
Only global/advanced settings:
- default IP mode
- default SNMP version
- timeout/retry defaults
- API/server URL if present
- firmware repository/source if present
- logging verbosity if present

Find and reconnect existing backend/API functionality for:
- config load/save
- run
- device/target detection
- firmware check
- firmware validation
- firmware upgrade
- firmware status/progress
- logs

Create/restore frontend adapters as needed:
- config adapter
- run adapter
- firmware adapter
- logs adapter

Use existing APIs where available.
If missing, make safe TODO placeholders.

State model:
Make or repair clear shared state for:
- active page
- target
- IP mode
- SNMP version
- SNMP credentials
- selected firmware
- detected firmware info
- firmware status
- upgrade status
- run status
- latest result
- logs
- settings

Visual direction:
Simple admin control center.
No tab maze.
No scattered settings buttons.
No duplicate run buttons.
No dead buttons.
No dense dashboard swamp.
No old broken UI in the primary flow.

Implementation rules:
- Find the active rendered UI and edit that.
- Remove the messy old active flow.
- Preserve backend logic where useful.
- Reconnect real functionality wherever possible.
- Add safe placeholders only when required.
- Run available checks from package.json.
- Fix what breaks.
- Commit useful checkpoints.

Acceptance criteria:
- Sidebar has Dashboard, Configure, Run, Firmware, Results, Logs, Settings.
- Active app visibly becomes Control Center.
- Firmware tab exists and shows firmware visibility.
- Firmware check works or safely reports TODO backend.
- Firmware validate works or safely reports TODO backend.
- Firmware upgrade requires confirmation.
- Configure supports target, IPv4/IPv6/Both, SNMPv2/SNMPv3.
- Run uses current config.
- Results update from run/firmware actions.
- Logs record major activity.
- Settings contains only global/advanced settings.
- No obvious disconnected buttons.
- No duplicate conflicting controls.
- Project builds or remaining errors are documented.

Final report:
Summarize:
1. Files changed
2. Active rendered entry point
3. Firmware restored/added
4. Config restored/added
5. Backend integrations used
6. TODO placeholders
7. Safety protections
8. Checks run
9. Known issues
PROMPT

cat > "$PROMPT_DIR/qa.md" <<'PROMPT'
Continue in YOLO mode.

Do a strict repair pass. Make the app work better.

Check and fix:
- visible buttons wired correctly
- Configure saves and persists state
- Run uses current config
- Firmware Check uses current config
- Firmware Validate requires firmware selection
- Firmware Upgrade requires confirmation
- failed validation blocks upgrade
- Results update after actions
- Logs record actions
- sidebar navigation works
- old messy UI is not the main flow
- build/lint/typecheck/test issues

Be decisive. Fix directly.
Run available checks.
Summarize what changed.
PROMPT

SECONDS_TOTAL=$(( HOURS * 60 * 60 ))
START_EPOCH=$(date +%s)
END_EPOCH=$(( START_EPOCH + SECONDS_TOTAL ))
PASS=1

run_pass() {
  local prompt_file="$1"
  local label="$2"
  local now remaining summary_file log_file

  now=$(date +%s)
  remaining=$(( END_EPOCH - now ))

  if [ "$remaining" -le 60 ]; then
    echo "Less than 60 seconds remaining. Stopping."
    return 1
  fi

  summary_file="$LOG_DIR/pass-$(printf "%02d" "$PASS")-$label-summary.md"
  log_file="$LOG_DIR/pass-$(printf "%02d" "$PASS")-$label.log"

  echo
  echo "============================================================"
  echo "PASS $PASS: $label"
  echo "Remaining seconds: $remaining"
  echo "============================================================"

  if command -v timeout >/dev/null 2>&1; then
    timeout --foreground "${remaining}s" \
      codex exec \
        --cd "$REPO_ROOT" \
        --yolo \
        --output-last-message "$summary_file" \
        - < "$prompt_file" 2>&1 | tee -a "$log_file"
  else
    codex exec \
      --cd "$REPO_ROOT" \
      --yolo \
      --output-last-message "$summary_file" \
      - < "$prompt_file" 2>&1 | tee -a "$log_file"
  fi

  echo
  echo "== Git status after pass $PASS =="
  git status --short | tee -a "$log_file"

  if ! git diff --quiet || ! git diff --cached --quiet; then
    git add -A
    git commit -m "YOLO Control Center pass $PASS: $label" || true
  else
    echo "No changes to commit."
  fi

  PASS=$(( PASS + 1 ))
}

while [ "$(date +%s)" -lt "$END_EPOCH" ]; do
  if [ $(( PASS % 2 )) -eq 1 ]; then
    run_pass "$PROMPT_DIR/main.md" "restore-control-center" || break
  else
    run_pass "$PROMPT_DIR/qa.md" "qa-repair" || break
  fi
done

echo
echo "============================================================"
echo "YOLO Control Center run complete."
echo "Branch: $BRANCH_NAME"
echo "Run dir: $RUN_DIR"
echo
echo "Final git status:"
git status --short
echo
echo "Recent commits:"
git log --oneline -10
echo "============================================================"
