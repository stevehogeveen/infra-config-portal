#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

"${SCRIPT_DIR}/codex-task.sh" ".codex/tasks/000-repo-audit.md"
