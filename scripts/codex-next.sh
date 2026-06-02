#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
QUEUE_FILE="${REPO_ROOT}/.codex/task-queue.md"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

if [[ ! -f "${QUEUE_FILE}" ]]; then
  echo "Error: queue file not found: ${QUEUE_FILE}" >&2
  exit 1
fi

next_task="$(
  sed -nE 's/^[[:space:]]*-[[:space:]]\[ \][[:space:]]+`?([^`[:space:]]+\.md)`?.*/\1/p' "${QUEUE_FILE}" \
    | head -n 1
)"

if [[ -z "${next_task}" ]]; then
  echo "No unchecked Codex tasks found in ${QUEUE_FILE}." >&2
  exit 0
fi

echo "Next Codex task: ${next_task}" >&2
"${SCRIPT_DIR}/codex-task.sh" "${next_task}"
