#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="${1:-.codex/tasks/030-overnight-mvp-buildout.md}"
RUN_MINUTES="${RUN_MINUTES:-480}"
MAX_ROUNDS="${MAX_ROUNDS:-60}"

cd "${REPO_ROOT}"

"${REPO_ROOT}/scripts/check-repo-root.sh"

if [[ ! -f "${TASK}" ]]; then
  echo "Error: task file not found: ${TASK}" >&2
  exit 1
fi

if [[ "${CODEX_SANDBOX_MODE:-}" != "danger-full-access" ]]; then
  echo "Error: overnight run requires explicit sandbox fallback." >&2
  echo "Run with:" >&2
  echo "  RUN_MINUTES=480 MAX_ROUNDS=60 CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND ./scripts/codex-overnight.sh" >&2
  exit 1
fi

if [[ "${CODEX_DANGER_ACK:-}" != "I_UNDERSTAND" ]]; then
  echo "Error: missing CODEX_DANGER_ACK=I_UNDERSTAND" >&2
  exit 1
fi

start_epoch="$(date +%s)"
stop_epoch="$((start_epoch + RUN_MINUTES * 60))"

mkdir -p .codex/runs

echo "== Codex overnight run =="
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
  echo "Overnight round ${round}/${MAX_ROUNDS} - $(date)"
  echo "============================================================"

  CODEX_SANDBOX_MODE=danger-full-access \
  CODEX_DANGER_ACK=I_UNDERSTAND \
  make codex-task TASK="${TASK}" || true

  echo
  echo "Running checks..."
  checks_ok=1

  if make -q provider-smoke >/dev/null 2>&1; then
    make provider-smoke || checks_ok=0
  else
    make provider-smoke || true
  fi

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
      git commit -m "Codex overnight MVP round ${round}"
    else
      echo "Checks passed. No changes to commit."
    fi
  else
    echo "Checks failed. Leaving changes uncommitted for inspection."
    echo "Stopping overnight run so the failure is visible."
    exit 1
  fi

  if [[ -f .codex/runs/latest.md ]]; then
    if grep -qi "no safe progress\|blocked\|nothing to do\|no changes\|cannot safely continue" .codex/runs/latest.md; then
      echo "Latest summary indicates blocked/no safe progress/no changes. Stopping."
      break
    fi
  fi

  round=$((round + 1))
done

echo
echo "== Overnight run finished =="
echo "Time: $(date)"

echo
echo "Latest Codex summary:"
if [[ -f .codex/runs/latest.md ]]; then
  echo "  .codex/runs/latest.md"
fi

echo
echo "Recent commits:"
git --no-pager log --oneline -20

echo
echo "Final status:"
git status --short

echo
echo "Final checks:"
make smoke
make test
make lint
