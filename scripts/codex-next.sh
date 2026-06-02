#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/codex-common.sh
. "${SCRIPT_DIR}/codex-common.sh"

REPO_ROOT="$(codex_repo_root_from_script_dir "${SCRIPT_DIR}")"
QUEUE_FILE="${REPO_ROOT}/.codex/task-queue.md"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

codex_warn_if_not_repo_root "${REPO_ROOT}"
cd "${REPO_ROOT}"

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
