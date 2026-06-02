#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
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
if [[ "${TASK_ARG}" = /* ]]; then
  TASK_FILE="${TASK_ARG}"
elif [[ -f "${PWD}/${TASK_ARG}" ]]; then
  TASK_FILE="${PWD}/${TASK_ARG}"
else
  TASK_FILE="${REPO_ROOT}/${TASK_ARG}"
fi

if [[ ! -f "${TASK_FILE}" ]]; then
  echo "Error: task file not found: ${TASK_ARG}" >&2
  exit 1
fi

TASK_REAL="$(realpath "${TASK_FILE}")"
ROOT_REAL="$(realpath "${REPO_ROOT}")"
case "${TASK_REAL}" in
  "${ROOT_REAL}"/*) ;;
  *)
    echo "Error: task file must be inside this repository: ${TASK_REAL}" >&2
    exit 1
    ;;
esac

clear_provider_environment() {
  local name
  while IFS='=' read -r name _; do
    case "${name}" in
      VSPHERE_*|VCENTER_*|GOVC_*|ESXI_*|ILO_*|REDFISH_*|NETAPP_*|ONTAP_*|NETBOX_*|NAUTOBOT_*|AWX_*|TOWER_*|ANSIBLE_*|TF_VAR_*|KUBECONFIG|AWS_*|AZURE_*|ARM_*|GOOGLE_*|GCLOUD_*|GCP_*)
        unset "${name}" || true
        ;;
    esac
  done < <(env)
  export PROVIDER_MODE=mock
}

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

clear_provider_environment
cd "${REPO_ROOT}"

echo "Running Codex task: ${TASK_REAL}" >&2
echo "Repository root: ${REPO_ROOT}" >&2
echo "Final response: ${final_file}" >&2

set +e
if [[ "${supports_json}" -eq 1 && "${supports_output}" -eq 1 ]]; then
  codex exec \
    --cd "${REPO_ROOT}" \
    --sandbox workspace-write \
    -c 'approval_policy="never"' \
    -c 'sandbox_workspace_write.network_access=false' \
    --json \
    -o "${final_file}" \
    - < "${TASK_REAL}" > "${jsonl_file}"
  status=$?
elif [[ "${supports_output}" -eq 1 ]]; then
  codex exec \
    --cd "${REPO_ROOT}" \
    --sandbox workspace-write \
    -c 'approval_policy="never"' \
    -c 'sandbox_workspace_write.network_access=false' \
    -o "${final_file}" \
    - < "${TASK_REAL}" > "${stdout_file}"
  status=$?
else
  codex exec \
    --cd "${REPO_ROOT}" \
    --sandbox workspace-write \
    -c 'approval_policy="never"' \
    -c 'sandbox_workspace_write.network_access=false' \
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
