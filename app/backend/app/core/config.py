from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

LAB_SUBNET_CIDR = "192.168.1.0/24"
LAB_ILO_IP = "192.168.1.201"
LAB_SERVER_EMBEDDED_NIC_IP = "192.168.1.202"
LAB_ESXI_MANAGEMENT_IP = "192.168.1.203"
LAB_CISCO_MANAGEMENT_IP = "192.168.1.204"
LAB_ANSIBLE_CONTROL_HOST_IP = "192.168.1.205"


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
                if key == "PROVIDER_MODE" or value is None:
                    continue
                existing = os.environ.get(key)
                if existing is not None:
                    if _is_stale_lab_ip(existing) and not _is_stale_lab_ip(value):
                        os.environ[key] = value
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


def _is_stale_lab_ip(value: str | None) -> bool:
    return bool(value and value.startswith("10.10.8."))


def _cisco_target_ip() -> str:
    value = _optional_env("CISCO_TARGET_IP") or _optional_env("ANSIBLE_CISCO_HOST")
    if _is_stale_lab_ip(value):
        return LAB_CISCO_MANAGEMENT_IP
    if value is None:
        return LAB_CISCO_MANAGEMENT_IP
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


def _media_inventory_dirs() -> tuple[str, ...]:
    if os.getenv("PROVIDER_MODE", "mock") == "mock":
        return ()
    return tuple(_split_csv(os.getenv("MEDIA_INVENTORY_DIRS", "")))


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "infra-config-portal")
    environment: str = os.getenv("ENVIRONMENT", "local")
    provider_mode: str = os.getenv("PROVIDER_MODE", "mock")
    media_inventory_dirs: tuple[str, ...] = _media_inventory_dirs()
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
    lab_subnet_cidr: str = os.getenv("LAB_SUBNET_CIDR", LAB_SUBNET_CIDR)
    server_embedded_nic_ip: str = os.getenv("SERVER_EMBEDDED_NIC_IP", LAB_SERVER_EMBEDDED_NIC_IP)
    ansible_control_host: str | None = _optional_env("ANSIBLE_CONTROL_HOST")
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
    cisco_console_transport: str = os.getenv("CISCO_CONSOLE_TRANSPORT", "local_serial")
    cisco_console_tcp_host: str | None = _optional_env("CISCO_CONSOLE_TCP_HOST")
    cisco_console_tcp_port: int = _int_env("CISCO_CONSOLE_TCP_PORT", 2001)
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
    lab_environment: str | None = _optional_env("LAB_ENVIRONMENT")
    lab_acknowledge_real_hardware: bool = _bool_env("LAB_ACKNOWLEDGE_REAL_HARDWARE", False)
    lab_acknowledge_device_reconfiguration: bool = _bool_env(
        "LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION",
        False,
    )
    lab_acknowledge_data_loss_risk: bool = _bool_env("LAB_ACKNOWLEDGE_DATA_LOSS_RISK", False)
    lab_acknowledge_lab_only: bool = _bool_env("LAB_ACKNOWLEDGE_LAB_ONLY", False)
    lab_allow_power_actions: bool = _bool_env("LAB_ALLOW_POWER_ACTIONS", False)
    lab_allow_firmware_updates: bool = _bool_env("LAB_ALLOW_FIRMWARE_UPDATES", False)
    lab_allow_factory_reset: bool = _bool_env("LAB_ALLOW_FACTORY_RESET", False)
    ilo_setup_apply_enabled: bool = _bool_env("ILO_SETUP_APPLY_ENABLED", False)
    cisco_console_apply_enabled: bool = _bool_env("CISCO_CONSOLE_APPLY_ENABLED", False)
    lab_apply_ack: str | None = _optional_env("LAB_APPLY_ACK")
    lab_target_ack: str | None = _optional_env("LAB_TARGET_ACK")
    lab_destructive_ack: str | None = _optional_env("LAB_DESTRUCTIVE_ACK")


settings = Settings()
