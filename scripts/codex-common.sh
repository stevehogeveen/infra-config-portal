#!/usr/bin/env bash

codex_repo_root_from_script_dir() {
  local script_dir="${1:?script dir required}"
  local candidate_root
  local git_root

  candidate_root="$(cd "${script_dir}/.." && pwd -P)"
  git_root="$(git -C "${candidate_root}" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -z "${git_root}" ]]; then
    echo "Error: no git repository root found for ${candidate_root}." >&2
    echo "Run this from a checkout of infra-config-portal." >&2
    return 1
  fi

  git_root="$(cd "${git_root}" && pwd -P)"
  if [[ "${git_root}" != "${candidate_root}" ]]; then
    echo "Error: script root mismatch." >&2
    echo "Script root: ${candidate_root}" >&2
    echo "Git root: ${git_root}" >&2
    return 1
  fi

  printf '%s\n' "${git_root}"
}

codex_warn_if_not_repo_root() {
  local repo_root="${1:?repo root required}"
  local current_dir

  current_dir="$(pwd -P)"
  if [[ "${current_dir}" != "${repo_root}" ]]; then
    echo "Notice: current directory is ${current_dir}; using repository root ${repo_root}." >&2
  fi
}

codex_resolve_repo_file() {
  local repo_root="${1:?repo root required}"
  local path_arg="${2:?path required}"
  local label="${3:-file}"
  local candidate
  local resolved

  if [[ "${path_arg}" = /* ]]; then
    candidate="${path_arg}"
  else
    candidate="${repo_root}/${path_arg}"
  fi

  if [[ ! -f "${candidate}" ]]; then
    echo "Error: ${label} not found: ${path_arg}" >&2
    echo "Relative paths are resolved from repository root: ${repo_root}" >&2
    return 1
  fi

  resolved="$(realpath "${candidate}")"
  case "${resolved}" in
    "${repo_root}"/*) ;;
    *)
      echo "Error: ${label} must be inside this repository: ${resolved}" >&2
      return 1
      ;;
  esac

  printf '%s\n' "${resolved}"
}

codex_clear_provider_environment() {
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

codex_validate_exec_safety() {
  local sandbox_mode="${CODEX_SANDBOX_MODE:-workspace-write}"

  case "${sandbox_mode}" in
    read-only|workspace-write|danger-full-access) ;;
    *)
      echo "Error: CODEX_SANDBOX_MODE must be read-only, workspace-write, or danger-full-access." >&2
      echo "Current value: ${sandbox_mode}" >&2
      return 2
      ;;
  esac

  if [[ "${sandbox_mode}" != "danger-full-access" ]]; then
    return 0
  fi

  if [[ "${CODEX_DANGER_ACK:-}" != "I_UNDERSTAND" ]]; then
    cat >&2 <<'EOF'
Error: CODEX_SANDBOX_MODE=danger-full-access disables Codex filesystem sandboxing.
This mode requires explicit acknowledgement:
  CODEX_SANDBOX_MODE=danger-full-access CODEX_DANGER_ACK=I_UNDERSTAND make codex-next

Use danger-full-access only on an isolated development machine with no real
infrastructure credentials, no secrets, no production SSH keys, and no access
to real vSphere, ESXi, iLO, NetApp, switches, DNS, IPAM, storage, or production
networks.
EOF
    return 1
  fi

  cat >&2 <<'EOF'
Warning: running Codex with danger-full-access. Filesystem sandboxing is disabled.
Only continue on an isolated development machine with no real infrastructure
credentials, no secrets, no production SSH keys, and no access to real vSphere,
ESXi, iLO, NetApp, switches, DNS, IPAM, storage, or production networks.
EOF
}
