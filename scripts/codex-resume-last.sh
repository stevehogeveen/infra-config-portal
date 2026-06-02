#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNS_DIR="${REPO_ROOT}/.codex/runs"
DEFAULT_PROMPT="${REPO_ROOT}/.codex/prompts/resume-last.md"

usage() {
  echo "Usage: $0 [prompt-file.md]" >&2
}

if [[ $# -gt 1 ]]; then
  usage
  exit 2
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "Error: Codex CLI is not installed or not on PATH." >&2
  echo "Install Codex, authenticate it, then retry this command." >&2
  exit 127
fi

PROMPT_ARG="${1:-${DEFAULT_PROMPT}}"
if [[ "${PROMPT_ARG}" = /* ]]; then
  PROMPT_FILE="${PROMPT_ARG}"
elif [[ -f "${PWD}/${PROMPT_ARG}" ]]; then
  PROMPT_FILE="${PWD}/${PROMPT_ARG}"
else
  PROMPT_FILE="${REPO_ROOT}/${PROMPT_ARG}"
fi

if [[ ! -f "${PROMPT_FILE}" ]]; then
  echo "Error: prompt file not found: ${PROMPT_ARG}" >&2
  exit 1
fi

PROMPT_REAL="$(realpath "${PROMPT_FILE}")"
ROOT_REAL="$(realpath "${REPO_ROOT}")"
case "${PROMPT_REAL}" in
  "${ROOT_REAL}"/*) ;;
  *)
    echo "Error: prompt file must be inside this repository: ${PROMPT_REAL}" >&2
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
prompt_base="$(basename "${PROMPT_REAL}")"
prompt_slug="${prompt_base%.*}"
prompt_slug="$(printf '%s' "${prompt_slug}" | tr -c 'A-Za-z0-9._-' '-')"
run_base="${timestamp}-resume-${prompt_slug}"
final_file="${RUNS_DIR}/${run_base}.md"
jsonl_file="${RUNS_DIR}/${run_base}.jsonl"
stdout_file="${RUNS_DIR}/${run_base}.stdout"

help_text="$(codex exec resume --help 2>&1 || true)"
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

echo "Resuming last Codex exec session with prompt: ${PROMPT_REAL}" >&2
echo "Repository root: ${REPO_ROOT}" >&2
echo "Final response: ${final_file}" >&2

set +e
if [[ "${supports_json}" -eq 1 && "${supports_output}" -eq 1 ]]; then
  codex exec resume \
    --last \
    -c 'sandbox_mode="workspace-write"' \
    -c 'approval_policy="never"' \
    -c 'sandbox_workspace_write.network_access=false' \
    --json \
    -o "${final_file}" \
    - < "${PROMPT_REAL}" > "${jsonl_file}"
  status=$?
elif [[ "${supports_output}" -eq 1 ]]; then
  codex exec resume \
    --last \
    -c 'sandbox_mode="workspace-write"' \
    -c 'approval_policy="never"' \
    -c 'sandbox_workspace_write.network_access=false' \
    -o "${final_file}" \
    - < "${PROMPT_REAL}" > "${stdout_file}"
  status=$?
else
  codex exec resume \
    --last \
    -c 'sandbox_mode="workspace-write"' \
    -c 'approval_policy="never"' \
    -c 'sandbox_workspace_write.network_access=false' \
    - < "${PROMPT_REAL}" | tee "${final_file}"
  status=${PIPESTATUS[0]}
fi
set -e

if [[ "${status}" -ne 0 ]]; then
  echo "Error: codex exec resume failed with exit code ${status}." >&2
  [[ -f "${jsonl_file}" ]] && echo "JSONL log: ${jsonl_file}" >&2
  [[ -f "${stdout_file}" ]] && echo "Stdout log: ${stdout_file}" >&2
  [[ -f "${final_file}" ]] && echo "Final response: ${final_file}" >&2
  exit "${status}"
fi

ln -sfn "$(basename "${final_file}")" "${RUNS_DIR}/latest.md"
if [[ -f "${jsonl_file}" ]]; then
  ln -sfn "$(basename "${jsonl_file}")" "${RUNS_DIR}/latest.jsonl"
fi

echo "Codex resume completed." >&2
echo "Final response: ${final_file}" >&2
[[ -f "${jsonl_file}" ]] && echo "JSONL log: ${jsonl_file}" >&2
