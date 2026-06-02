#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/codex-common.sh
. "${SCRIPT_DIR}/codex-common.sh"

REPO_ROOT="$(codex_repo_root_from_script_dir "${SCRIPT_DIR}")"
CURRENT_DIR="$(pwd -P)"

if [[ "${CURRENT_DIR}" != "${REPO_ROOT}" ]]; then
  echo "Error: Run this from ${REPO_ROOT}, not ${CURRENT_DIR}." >&2
  exit 2
fi
