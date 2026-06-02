#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="${1:-.codex/tasks/010-until-5pm-big-mvp-push.md}"
STOP_TIME="${STOP_TIME:-17:00}"
MAX_ROUNDS="${MAX_ROUNDS:-12}"

cd "${REPO_ROOT}"

if [[ ! -x "${REPO_ROOT}/scripts/check-repo-root.sh" ]]; then
  echo "Error: scripts/check-repo-root.sh missing or not executable." >&2
  exit 1
fi

"${REPO_ROOT}/scripts/check-repo-root.sh"

if [[ ! -f "${TASK}" ]]; then
  echo "Error: task file not found: ${TASK}" >&2
  exit 1
fi

if [[ "${CODEX_SANDBOX_MODE:-}" != "danger-full-access" ]]; then
  echo "Error: this long run requires explicit sandbox fallback." >&2
  echo "Run with:" >&2
  echo "  CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND ./scripts/codex-until-5pm.sh" >&2
  exit 1
fi

if [[ "${CODEX_DANGER_ACK:-}" != "I_UNDERSTAND" ]]; then
  echo "Error: missing CODEX_DANGER_ACK=I_UNDERSTAND" >&2
  exit 1
fi

stop_epoch="$(date -d "today ${STOP_TIME}" +%s)"
now_epoch="$(date +%s)"

if (( now_epoch >= stop_epoch )); then
  echo "It is already past ${STOP_TIME}. Nothing to run."
  exit 0
fi

mkdir -p .codex/runs

echo "== Codex long run =="
echo "Repo: ${REPO_ROOT}"
echo "Task: ${TASK}"
echo "Stop time: ${STOP_TIME}"
echo "Max rounds: ${MAX_ROUNDS}"
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
      git commit -m "Codex MVP push round ${round}"
    else
      echo "Checks passed. No changes to commit."
    fi
  else
    echo "Checks failed. Leaving changes uncommitted for inspection."
    echo "Stopping long run so the failure is not buried under more changes."
    exit 1
  fi

  if [[ -z "$(git status --short)" ]]; then
    recent_summary=""
    if [[ -f .codex/runs/latest.md ]]; then
      recent_summary="$(cat .codex/runs/latest.md)"
    fi

    if grep -qi "no changes\|nothing to do\|no safe progress\|blocked" <<< "${recent_summary}"; then
      echo "Latest summary indicates no safe progress or blocked state. Stopping."
      break
    fi
  fi

  round=$((round + 1))
done

echo
echo "== Long run finished =="
echo "Time: $(date)"
echo
echo "Latest Codex summary:"
if [[ -f .codex/runs/latest.md ]]; then
  echo "  .codex/runs/latest.md"
else
  echo "  no latest.md found"
fi

echo
echo "Recent commits:"
git --no-pager log --oneline -8

echo
echo "Final status:"
git status --short
