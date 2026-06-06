#!/usr/bin/env bash
set -euo pipefail

cd /home/administrator/infra-config-portal

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="artifacts/codex-runs"
LOG_FILE="$LOG_DIR/overnight-lab-builder-${RUN_ID}.log"
PROMPT_FILE="/tmp/overnight-lab-builder-${RUN_ID}.txt"

mkdir -p "$LOG_DIR"

git status --short > "$LOG_DIR/overnight-pre-status-${RUN_ID}.txt" || true
git diff > "$LOG_DIR/overnight-pre-working-tree-${RUN_ID}.patch" || true

cat > "$PROMPT_FILE" <<'PROMPT'
We are doing an overnight real-lab automation run.

Work only in:
/home/administrator/infra-config-portal

Use:
PROVIDER_MODE=local-lab-readwrite
.env.local.real-lab

Overall goal:
Make the app a real Lab Builder, not a report-only dashboard. Remove fake blockers, run real lab workflows, fix failures, harden failure handling, and leave a clear final report.

Current priority:
The previous `make provider-lab-full-rebuild` was implemented as a report-only summary and blocked real device calls because it detected automated Codex context. That is wrong for the real lab execution path.

Required first fix:
Split the workflow into:

1. `make provider-lab-full-rebuild-summary`
   - report-only
   - no real device calls
   - dashboard summary only

2. `make provider-lab-full-rebuild`
   - real lab execution
   - uses PROVIDER_MODE=local-lab-readwrite
   - loads .env.local.real-lab
   - calls live Cisco, iLO, RAID, and ESXi workflows
   - does not block only because the caller is Codex or codex exec
   - stops only on real physical/config blockers

After that, run the real full rebuild path as far as possible.

Known lab state:
- iLO target: 192.168.1.201
- Server: HPE ProLiant DL360 Gen10
- iLO: iLO 5 firmware 3.19
- Smart Array P408i-a detected
- RAID live validation previously succeeded
- ESXi boot workflow previously completed
- Cisco console auto-discovery works
- Cisco prompt detection works at 9600 baud
- Cisco credentials and enable password exist in .env.local.real-lab
- Real-lab IP profile: iLO 192.168.1.201, server embedded NIC 192.168.1.202, ESXi 192.168.1.203, Cisco 192.168.1.204, Ansible/control host 192.168.1.205
- Cisco target management IP: 192.168.1.204
- Cisco management is not configured yet
- Cisco current blocker: exec prompt reached, privileged exec not confirmed

Overnight run stages:

Stage 1: Baseline
- Check git status.
- Save changed file summary.
- Read current reports under artifacts/codex-runs.
- Save baseline report.

Stage 2: Fix full rebuild blocker
- Remove automated-Codex-context blocker from the real execution target.
- Keep report-only behavior under provider-lab-full-rebuild-summary.
- Update Makefiles, docs, API, UI labels, and tests.
- Prove real execution target calls live stages.

Stage 3: Cisco real rebuild
- Auto-discover USB console every run.
- Try /dev/serial/by-id, /dev/ttyUSB*, /dev/ttyACM*.
- Try baud rates 9600, 19200, 38400, 57600, 115200.
- Reach prompt.
- Diagnose and fix privilege escalation path.
- Use .env.local.real-lab credentials without printing secrets.
- If privileged exec works, apply Cisco bootstrap:
  - hostname
  - management VLAN/interface
  - management IP 192.168.1.204 if configured
  - gateway
  - local admin user
  - enable secret
  - SSH version 2
  - SCP readiness if supported
  - line console/vty login local
  - LLDP
- Save config.
- Reload only if needed.
- Validate ping, SSH, SCP.
- Save Cisco reports.

Stage 4: HPE/iLO/RAID validation
- Refresh iLO reachability/auth/inventory.
- Confirm DL360 Gen10/iLO 5/Redfish/health/power.
- Validate RAID layout.
- If RAID does not match saved intent, run plan/apply/reset/validate workflow.
- Save reports.

Stage 5: ESXi workflow
- Confirm media inventory.
- Select preferred HPE ESXi 8.0.3 ISO unless config says otherwise.
- Validate media URL reachable by iLO.
- Insert ISO through iLO VirtualMedia.
- Set one-time boot.
- Reset/boot server if needed.
- Detect ESXi installer or ESXi host state.
- Save reports.

Stage 6: Product Verification / Build Certification
Build or improve a verification system that checks the small but critical stuff:
- username/password compatibility across iLO, Cisco, ESXi, NetApp, app config, shell, JSON, YAML, Ansible
- special character handling
- MTU consistency between Cisco, ESXi, NetApp, iSCSI, vMotion, management, and backup paths
- protocol choices and readiness:
  - iLO Redfish/XML fallback
  - Cisco console/SSH/SCP
  - ESXi API/SSH
  - NetApp REST/SSH
  - ISO HTTP media serving
- required port reachability
- post-build validation checklist
- failure classification and exact next action

Implement:
- backend verification service
- Makefile target: `make provider-lab-build-verification`
- report: artifacts/codex-runs/build-verification-report.md
- UI panel: Build Verification / Product Certification
- tests for credential escaping, MTU validation, protocol readiness, and failure reporting

Stage 7: UI and tests
- Update Provider Status UI so it shows:
  - real full rebuild execution
  - report-only summary
  - Cisco console/bootstrap/Ethernet status
  - iLO inventory
  - RAID status
  - ESXi media/boot/install status
  - Build Verification/Product Certification
- Run backend tests.
- Run frontend build.
- Save screenshots if possible.

Final output:
Save the main report to:
artifacts/codex-runs/overnight-lab-builder-final-report.md

Also save:
artifacts/codex-runs/overnight-lab-builder-summary-redacted.json

Keep working until timeout or a real blocker.
When blocked, improve the app/reporting so the blocker is obvious.
Do not use mock results as substitutes for real lab results.
Do not print secrets.
PROMPT

echo "Starting overnight lab builder run: $RUN_ID"
echo "Log: $LOG_FILE"
echo "Prompt: $PROMPT_FILE"

timeout 8h codex exec \
  --sandbox danger-full-access \
  "$(cat "$PROMPT_FILE")" \
  2>&1 | tee "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo "Codex exit code: $EXIT_CODE" | tee -a "$LOG_FILE"
git status --short > "$LOG_DIR/overnight-post-status-${RUN_ID}.txt" || true
git diff > "$LOG_DIR/overnight-post-working-tree-${RUN_ID}.patch" || true

exit "$EXIT_CODE"
