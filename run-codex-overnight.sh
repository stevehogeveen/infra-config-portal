#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

mkdir -p .codex/runs

timestamp="$(date +%Y%m%d-%H%M%S)"
log_file=".codex/runs/overnight-${timestamp}.log"
summary_file=".codex/runs/overnight-${timestamp}-summary.md"
final_file=".codex/runs/overnight-${timestamp}-final.md"
prompt_file="$(mktemp "${TMPDIR:-/tmp}/codex-overnight.XXXXXX.md")"
trap 'rm -f "$prompt_file"' EXIT

: "${CODEX_SANDBOX_MODE:=workspace-write}"
: "${CODEX_APPROVAL_POLICY:=never}"

if [[ "$CODEX_SANDBOX_MODE" == "danger-full-access" ]]; then
  if [[ "${CODEX_DANGER_ACK:-}" != "I_UNDERSTAND" ]]; then
    echo "Refusing danger-full-access without CODEX_DANGER_ACK=I_UNDERSTAND" >&2
    exit 2
  fi
elif [[ "$CODEX_SANDBOX_MODE" != "workspace-write" && "$CODEX_SANDBOX_MODE" != "read-only" ]]; then
  echo "Unsupported CODEX_SANDBOX_MODE: $CODEX_SANDBOX_MODE" >&2
  exit 2
fi

if [[ "$CODEX_APPROVAL_POLICY" != "never" ]]; then
  echo "Unsupported CODEX_APPROVAL_POLICY for unattended runs: $CODEX_APPROVAL_POLICY" >&2
  exit 2
fi

if [[ ! -f .codex/overnight-system-prompt.md || ! -f .codex/overnight-queue.md ]]; then
  echo "Missing .codex/overnight-system-prompt.md or .codex/overnight-queue.md" >&2
  exit 2
fi

git_status_before="$(git status --short --branch)"
git_head_before="$(git log -1 --oneline)"

{
  echo "# Codex Overnight Summary"
  echo
  echo "- Started: $(date -Is)"
  echo "- Worktree: $ROOT"
  echo "- Sandbox: $CODEX_SANDBOX_MODE"
  echo "- Approval policy: $CODEX_APPROVAL_POLICY"
  echo "- Runner command: ./run-codex-overnight.sh"
  echo "- System prompt: .codex/overnight-system-prompt.md"
  echo "- Queue: .codex/overnight-queue.md"
  echo "- Log: $log_file"
  echo "- Final response: $final_file"
  echo
  echo "## Git Before"
  echo
  echo '```text'
  echo "$git_status_before"
  echo "$git_head_before"
  echo '```'
} > "$summary_file"

{
  echo "# System Prompt"
  cat .codex/overnight-system-prompt.md
  echo
  echo "# Overnight Queue"
  cat .codex/overnight-queue.md
} > "$prompt_file"

if [[ "${CODEX_OVERNIGHT_SMOKE:-}" == "1" ]]; then
  {
    echo
    echo "## Smoke Result"
    echo
    echo "Smoke mode validated files and wrote this summary without invoking Codex."
    echo
    echo "This was a dry smoke invocation. No long overnight run was started."
    echo
    echo "## Git After"
    echo
    echo '```text'
    git status --short --branch
    git log -5 --oneline
    echo '```'
    echo
    echo "- Finished: $(date -Is)"
  } >> "$summary_file"
  echo "Smoke summary written to $summary_file"
  exit 0
fi

set +e
codex exec \
  -C "$ROOT" \
  -s "$CODEX_SANDBOX_MODE" \
  -c "approval_policy=\"${CODEX_APPROVAL_POLICY}\"" \
  -o "$final_file" \
  - < "$prompt_file" 2>&1 | tee "$log_file"
codex_status=${PIPESTATUS[0]}
set -e

{
  echo
  echo "## Codex Exit"
  echo
  echo "- Exit status: $codex_status"
  echo
  echo "## Git After"
  echo
  echo '```text'
  git status --short --branch
  echo
  git log -5 --oneline
  echo '```'
  echo
  echo "## Paste-Back Checklist"
  echo
  echo "- Review this summary."
  echo "- Review $final_file."
  echo "- Review $log_file if Codex stopped, failed, or left changes uncommitted."
  echo "- Confirm whether each clean slice was tested and committed separately."
  echo "- Confirm real hardware write/destructive actions stayed blocked."
  echo "- Run `git status --short --branch` before continuing manual work."
  echo
  echo "- Finished: $(date -Is)"
} >> "$summary_file"

echo "Summary written to $summary_file"
echo "Log written to $log_file"
echo "Final response written to $final_file"
exit "$codex_status"
