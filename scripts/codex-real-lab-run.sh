#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="${1:-.codex/tasks/040-real-lab-ilo-cisco-esxi-validation.md}"
RUN_MINUTES="${RUN_MINUTES:-180}"
MAX_ROUNDS="${MAX_ROUNDS:-18}"

cd "${REPO_ROOT}"

"${REPO_ROOT}/scripts/check-repo-root.sh"

if [[ ! -f .env.local.real-lab ]]; then
  echo "Missing .env.local.real-lab. Run ./scripts/setup-real-lab-env.sh first." >&2
  exit 1
fi

set -a
source .env.local.real-lab
set +a

if [[ "${LAB_CLOSED_LOOP_ACK:-}" != "YES" ]]; then
  echo "LAB_CLOSED_LOOP_ACK must be YES." >&2
  exit 1
fi

if [[ "${LAB_READONLY_ACK:-}" != "YES" ]]; then
  echo "LAB_READONLY_ACK must be YES." >&2
  exit 1
fi

if [[ "${CODEX_SANDBOX_MODE:-}" != "danger-full-access" ]]; then
  echo "Run with CODEX_SANDBOX_MODE=danger-full-access." >&2
  exit 1
fi

if [[ "${CODEX_DANGER_ACK:-}" != "I_UNDERSTAND" ]]; then
  echo "Run with CODEX_DANGER_ACK=I_UNDERSTAND." >&2
  exit 1
fi

mkdir -p artifacts/real-lab .codex/runs

start_epoch="$(date +%s)"
stop_epoch="$((start_epoch + RUN_MINUTES * 60))"

echo "== Real lab Codex run =="
echo "Repo: ${REPO_ROOT}"
echo "Task: ${TASK}"
echo "Run minutes: ${RUN_MINUTES}"
echo "Max rounds: ${MAX_ROUNDS}"
echo "Stop around: $(date -d "@${stop_epoch}")"
echo "Closed loop: ${LAB_CLOSED_LOOP_ACK}"
echo "Read-only: ${LAB_READONLY_ACK}"
echo "Destructive/rebuild: ${LAB_DESTRUCTIVE_ACK:-disabled}"
echo

round=1

while (( $(date +%s) < stop_epoch && round <= MAX_ROUNDS )); do
  echo
  echo "============================================================"
  echo "Real lab round ${round}/${MAX_ROUNDS} - $(date)"
  echo "============================================================"

  set -a
  source .env.local.real-lab
  set +a

  CODEX_SANDBOX_MODE=danger-full-access \
  CODEX_DANGER_ACK=I_UNDERSTAND \
  make codex-task TASK="${TASK}" || true

  echo
  echo "Running quality gates..."
  checks_ok=1

  make provider-smoke || true
  make smoke || checks_ok=0
  make test || checks_ok=0
  make lint || checks_ok=0
  git diff --check || checks_ok=0

  echo
  echo "Git status:"
  git status --short

  if [[ "${checks_ok}" -eq 1 ]]; then
    if [[ -n "$(git status --short | grep -v '^?? artifacts/' || true)" ]]; then
      echo "Checks passed. Committing source changes."
      git add .
      git reset .env.local.real-lab 2>/dev/null || true
      git reset artifacts/real-lab 2>/dev/null || true
      git commit -m "Codex real lab validation round ${round}"
    else
      echo "Checks passed. No source changes to commit."
    fi
  else
    echo "Checks failed. Stopping with changes uncommitted."
    exit 1
  fi

  if [[ -f .codex/runs/latest.md ]]; then
    if grep -qi "cannot safely continue\|blocked and stopped\|no safe progress\|nothing to do" .codex/runs/latest.md; then
      echo "Latest summary indicates blocked/no safe progress. Stopping."
      break
    fi
  fi

  round=$((round + 1))
done

echo
echo "== Real lab run finished =="
date
echo
echo "Latest Codex summary:"
cat .codex/runs/latest.md 2>/dev/null || true
echo
echo "Recent commits:"
git --no-pager log --oneline -12
echo
echo "Final status:"
git status --short
