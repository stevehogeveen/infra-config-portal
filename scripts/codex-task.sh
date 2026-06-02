#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/codex-common.sh
. "${SCRIPT_DIR}/codex-common.sh"

REPO_ROOT="$(codex_repo_root_from_script_dir "${SCRIPT_DIR}")"
RUNS_DIR="${REPO_ROOT}/.codex/runs"

usage() {
  echo "Usage: $0 <task-file.md>" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "Error: Codex CLI is not installed or not on PATH." >&2
  echo "Install Codex, authenticate it, then retry this command." >&2
  exit 127
fi

TASK_ARG="$1"
TASK_REAL="$(codex_resolve_repo_file "${REPO_ROOT}" "${TASK_ARG}" "task file")"

CODEX_SANDBOX_MODE="${CODEX_SANDBOX_MODE:-workspace-write}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-never}"

codex_warn_if_not_repo_root "${REPO_ROOT}"
codex_validate_exec_safety
cd "${REPO_ROOT}"
mkdir -p "${RUNS_DIR}"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
task_base="$(basename "${TASK_REAL}")"
task_slug="${task_base%.*}"
task_slug="$(printf '%s' "${task_slug}" | tr -c 'A-Za-z0-9._-' '-')"
run_base="${timestamp}-${task_slug}"
final_file="${RUNS_DIR}/${run_base}.md"
jsonl_file="${RUNS_DIR}/${run_base}.jsonl"
stdout_file="${RUNS_DIR}/${run_base}.stdout"

help_text="$(codex exec --help 2>&1 || true)"
supports_json=0
supports_output=0
if grep -q -- '--json' <<<"${help_text}"; then
  supports_json=1
fi
if grep -q -- '--output-last-message' <<<"${help_text}"; then
  supports_output=1
fi

codex_clear_provider_environment

codex_config_args=(
  -c "approval_policy=\"${CODEX_APPROVAL_POLICY}\""
  -c 'sandbox_workspace_write.network_access=false'
)

echo "Running Codex task: ${TASK_REAL}" >&2
echo "Repository root: ${REPO_ROOT}" >&2
echo "Codex sandbox mode: ${CODEX_SANDBOX_MODE}" >&2
echo "Codex approval policy: ${CODEX_APPROVAL_POLICY}" >&2
echo "Final response: ${final_file}" >&2

set +e
if [[ "${supports_json}" -eq 1 && "${supports_output}" -eq 1 ]]; then
  codex exec \
    --cd "${REPO_ROOT}" \
    --sandbox "${CODEX_SANDBOX_MODE}" \
    "${codex_config_args[@]}" \
    --json \
    -o "${final_file}" \
    - < "${TASK_REAL}" > "${jsonl_file}"
  status=$?
elif [[ "${supports_output}" -eq 1 ]]; then
  codex exec \
    --cd "${REPO_ROOT}" \
    --sandbox "${CODEX_SANDBOX_MODE}" \
    "${codex_config_args[@]}" \
    -o "${final_file}" \
    - < "${TASK_REAL}" > "${stdout_file}"
  status=$?
else
  codex exec \
    --cd "${REPO_ROOT}" \
    --sandbox "${CODEX_SANDBOX_MODE}" \
    "${codex_config_args[@]}" \
    - < "${TASK_REAL}" | tee "${final_file}"
  status=${PIPESTATUS[0]}
fi
set -e

if [[ "${status}" -ne 0 ]]; then
  echo "Error: codex exec failed with exit code ${status}." >&2
  [[ -f "${jsonl_file}" ]] && echo "JSONL log: ${jsonl_file}" >&2
  [[ -f "${stdout_file}" ]] && echo "Stdout log: ${stdout_file}" >&2
  [[ -f "${final_file}" ]] && echo "Final response: ${final_file}" >&2
  exit "${status}"
fi

ln -sfn "$(basename "${final_file}")" "${RUNS_DIR}/latest.md"
if [[ -f "${jsonl_file}" ]]; then
  ln -sfn "$(basename "${jsonl_file}")" "${RUNS_DIR}/latest.jsonl"
fi

echo "Codex task completed." >&2
echo "Final response: ${final_file}" >&2
[[ -f "${jsonl_file}" ]] && echo "JSONL log: ${jsonl_file}" >&2
