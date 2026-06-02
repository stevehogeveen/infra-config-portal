#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="${1:-.codex/tasks/013-two-hour-ui-operator-flow-push.md}"
RUN_MINUTES="${RUN_MINUTES:-120}"
MAX_ROUNDS="${MAX_ROUNDS:-24}"

cd "${REPO_ROOT}"

"${REPO_ROOT}/scripts/check-repo-root.sh"

if [[ ! -f "${TASK}" ]]; then
  echo "Error: task file not found: ${TASK}" >&2
  exit 1
fi

if [[ "${CODEX_SANDBOX_MODE:-}" != "danger-full-access" ]]; then
  echo "Error: timed run requires explicit sandbox fallback." >&2
  echo "Run with:" >&2
  echo "  RUN_MINUTES=120 CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND ./scripts/codex-timed-run.sh" >&2
  exit 1
fi

if [[ "${CODEX_DANGER_ACK:-}" != "I_UNDERSTAND" ]]; then
  echo "Error: missing CODEX_DANGER_ACK=I_UNDERSTAND" >&2
  exit 1
fi

start_epoch="$(date +%s)"
stop_epoch="$((start_epoch + RUN_MINUTES * 60))"

mkdir -p .codex/runs

echo "== Codex timed run =="
echo "Repo: ${REPO_ROOT}"
echo "Task: ${TASK}"
echo "Run minutes: ${RUN_MINUTES}"
echo "Max rounds: ${MAX_ROUNDS}"
echo "Stop around: $(date -d "@${stop_epoch}")"
echo

round=1

while (( $(date +%s) < stop_epoch && round <= MAX_ROUNDS )); do
  echo
  echo "============================================================"
  echo "Round ${round}/${MAX_ROUNDS} - $(date)"
  echo "============================================================"

  CODEX_SANDBOX_MODE=danger-full-access \
  CODEX_DANGER_ACK=I_UNDERSTAND \
  make codex-task TASK="${TASK}" || true

  echo
  echo "Running checks..."
  checks_ok=1

  make smoke || checks_ok=0
  make test || checks_ok=0
  make lint || checks_ok=0
  git diff --check || checks_ok=0

  echo
  echo "Git status:"
  git status --short

  if [[ "${checks_ok}" -eq 1 ]]; then
    if [[ -n "$(git status --short)" ]]; then
      echo "Checks passed. Committing changes."
      git add .
      git commit -m "Codex timed run round ${round}"
    else
      echo "Checks passed. No changes to commit."
    fi
  else
    echo "Checks failed. Leaving changes uncommitted for inspection."
    echo "Stopping timed run so the failure is not buried under more changes."
    exit 1
  fi

  if [[ -f .codex/runs/latest.md ]]; then
    if grep -qi "no safe progress\|blocked\|nothing to do\|no changes" .codex/runs/latest.md; then
      echo "Latest summary indicates blocked/no safe progress/no changes. Stopping."
      break
    fi
  fi

  round=$((round + 1))
done

echo
echo "== Timed run finished =="
echo "Time: $(date)"
echo
echo "Latest Codex summary:"
if [[ -f .codex/runs/latest.md ]]; then
  echo "  .codex/runs/latest.md"
fi

echo
echo "Recent commits:"
git --no-pager log --oneline -10

echo
echo "Final status:"
git status --short
