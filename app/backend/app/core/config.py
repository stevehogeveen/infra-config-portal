from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


def _load_local_real_lab_env() -> None:
    candidates: list[Path] = []
    cwd = Path.cwd()
    repo_root = Path(__file__).resolve().parents[4]
    app_root = repo_root / "app"
    backend_root = app_root / "backend"

    for base in (cwd, cwd.parent, cwd.parent.parent, backend_root, app_root, repo_root):
        env_file = base / ".env.local.real-lab"
        if env_file not in candidates:
            candidates.append(env_file)

    for env_file in candidates:
        if env_file.exists():
            for key, value in dotenv_values(env_file).items():
                if key == "PROVIDER_MODE" or value is None or key in os.environ:
                    continue
                os.environ[key] = value


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _cisco_target_ip() -> str:
    value = _optional_env("CISCO_TARGET_IP") or _optional_env("ANSIBLE_CISCO_HOST")
    if value == "10.10.8.112" or value is None:
        return "192.168.1.220"
    return value


def _cisco_management_prefix() -> str:
    value = _optional_env("CISCO_MANAGEMENT_PREFIX")
    if value is None:
        return "/24"
    return "/24" if value == "255.255.255.0" else value


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


_load_local_real_lab_env()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "infra-config-portal")
    environment: str = os.getenv("ENVIRONMENT", "local")
    provider_mode: str = os.getenv("PROVIDER_MODE", "mock")
    media_inventory_dirs: tuple[str, ...] = tuple(
        _split_csv(os.getenv("MEDIA_INVENTORY_DIRS", ""))
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./.local/infra_config_portal.db",
    )
    cors_origins: tuple[str, ...] = tuple(
        _split_csv(os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"))
    )
    ilo_test_host: str | None = _optional_env("ILO_TEST_HOST")
    ilo_test_username: str | None = _optional_env("ILO_TEST_USERNAME")
    ilo_test_password: str | None = _optional_env("ILO_TEST_PASSWORD")
    ilo_test_verify_tls: bool = _bool_env(
        "ILO_TEST_VERIFY_TLS",
        _bool_env("ILO_REDFISH_VERIFY_TLS", True),
    )
    ilo_test_timeout_seconds: float = _float_env("ILO_TEST_TIMEOUT_SECONDS", 3.0)
    esxi_test_host: str | None = _optional_env("ESXI_TEST_HOST")
    esxi_test_username: str | None = _optional_env("ESXI_TEST_USERNAME")
    esxi_test_password: str | None = _optional_env("ESXI_TEST_PASSWORD")
    esxi_configured: bool = _bool_env("ESXI_CONFIGURED", False)
    esxi_test_verify_tls: bool = _bool_env("ESXI_TEST_VERIFY_TLS", True)
    esxi_test_timeout_seconds: float = _float_env("ESXI_TEST_TIMEOUT_SECONDS", 3.0)
    esxi_test_ssh_timeout_seconds: float = _float_env("ESXI_TEST_SSH_TIMEOUT_SECONDS", 3.0)
    cisco_target_ip: str | None = _cisco_target_ip()
    cisco_test_username: str | None = (
        _optional_env("CISCO_TEST_USERNAME")
        or _optional_env("ANSIBLE_CISCO_USERNAME")
        or _optional_env("LAB_USERNAME")
    )
    cisco_test_password: str | None = (
        _optional_env("CISCO_TEST_PASSWORD")
        or _optional_env("ANSIBLE_CISCO_PASSWORD")
        or _optional_env("LAB_PASSWORD")
    )
    cisco_enable_password: str | None = _optional_env("CISCO_ENABLE_PASSWORD") or _optional_env(
        "ANSIBLE_CISCO_ENABLE_PASSWORD"
    )
    cisco_mgmt_configured: bool = _bool_env("CISCO_MGMT_CONFIGURED", False)
    cisco_management_prefix: str | None = _cisco_management_prefix()
    cisco_management_gateway: str | None = _optional_env("CISCO_MANAGEMENT_GATEWAY")
    cisco_management_vlan: str | None = _optional_env("CISCO_MANAGEMENT_VLAN")
    cisco_management_interface: str | None = _optional_env("CISCO_MANAGEMENT_INTERFACE")
    cisco_management_strategy: str | None = _optional_env("CISCO_MANAGEMENT_STRATEGY")
    cisco_hostname: str | None = _optional_env("CISCO_HOSTNAME")
    cisco_domain_name: str | None = _optional_env("CISCO_DOMAIN_NAME")
    cisco_dns_servers: tuple[str, ...] = tuple(_split_csv(os.getenv("CISCO_DNS_SERVERS", "")))
    ansible_cisco_network_os: str = os.getenv("ANSIBLE_CISCO_NETWORK_OS", "cisco.ios.ios")
    ansible_cisco_connection: str = os.getenv(
        "ANSIBLE_CISCO_CONNECTION",
        "ansible.netcommon.network_cli",
    )
    ansible_cisco_timeout_seconds: float = _float_env("ANSIBLE_CISCO_TIMEOUT_SECONDS", 8.0)
    cisco_console_port: str | None = _optional_env("CISCO_CONSOLE_PORT")
    cisco_console_baud: int = _int_env("CISCO_CONSOLE_BAUD", 9600)
    cisco_console_timeout_seconds: float = _float_env("CISCO_CONSOLE_TIMEOUT_SECONDS", 2.0)
    cisco_console_prompt_settle_seconds: float = _float_env(
        "CISCO_CONSOLE_PROMPT_SETTLE_SECONDS",
        0.5,
    )
    cisco_console_prompt_read_window_seconds: float = _float_env(
        "CISCO_CONSOLE_PROMPT_READ_WINDOW_SECONDS",
        1.0,
    )
    cisco_console_prompt_max_bytes: int = _int_env("CISCO_CONSOLE_PROMPT_MAX_BYTES", 8192)
    netapp_configured: bool = _bool_env("NETAPP_CONFIGURED", False)
    netapp_controller_a_sp: str = os.getenv("NETAPP_CONTROLLER_A_SP", "10.10.8.13")
    netapp_controller_b_sp: str = os.getenv("NETAPP_CONTROLLER_B_SP", "10.10.8.14")
    netapp_cluster_mgmt_ip: str = os.getenv("NETAPP_CLUSTER_MGMT_IP", "10.10.8.45")
    netapp_node_a_mgmt_ip: str = os.getenv("NETAPP_NODE_A_MGMT_IP", "10.10.8.46")
    netapp_node_b_mgmt_ip: str = os.getenv("NETAPP_NODE_B_MGMT_IP", "10.10.8.47")
    netapp_svm_mgmt_ip: str = os.getenv("NETAPP_SVM_MGMT_IP", "10.10.8.48")
    netapp_iscsi_lifs: tuple[str, ...] = tuple(
        _split_csv(os.getenv("NETAPP_ISCSI_LIFS", "10.10.8.51,10.10.8.52,10.10.8.53,10.10.8.54"))
    )
    netapp_api_username: str | None = _optional_env("NETAPP_API_USERNAME")
    netapp_api_password: str | None = _optional_env("NETAPP_API_PASSWORD")
    netapp_api_verify_tls: bool = _bool_env("NETAPP_API_VERIFY_TLS", True)
    netapp_current_ontap_version: str | None = _optional_env("NETAPP_CURRENT_ONTAP_VERSION")
    lab_closed_loop_ack: str | None = _optional_env("LAB_CLOSED_LOOP_ACK")
    lab_readonly_ack: str | None = _optional_env("LAB_READONLY_ACK")
    cisco_console_apply_enabled: bool = _bool_env("CISCO_CONSOLE_APPLY_ENABLED", False)
    lab_apply_ack: str | None = _optional_env("LAB_APPLY_ACK")
    lab_target_ack: str | None = _optional_env("LAB_TARGET_ACK")
    lab_destructive_ack: str | None = _optional_env("LAB_DESTRUCTIVE_ACK")


settings = Settings()
