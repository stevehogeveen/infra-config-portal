from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from app.services.path_utils import path_exists

LAB_SUBNET_CIDR = "192.168.1.0/24"
LAB_ILO_IP = "192.168.1.201"
LAB_SERVER_EMBEDDED_NIC_IP = "192.168.1.202"
LAB_ESXI_MANAGEMENT_IP = "192.168.1.203"
LAB_CISCO_MANAGEMENT_IP = "192.168.1.204"
LAB_ANSIBLE_CONTROL_HOST_IP = "192.168.1.205"
LAB_NETAPP_CONTROLLER_A_SP_IP = "192.168.1.210"
LAB_NETAPP_CONTROLLER_B_SP_IP = "192.168.1.211"
LAB_NETAPP_CLUSTER_MGMT_IP = "192.168.1.220"
LAB_NETAPP_NODE_A_MGMT_IP = "192.168.1.221"
LAB_NETAPP_NODE_B_MGMT_IP = "192.168.1.222"
LAB_NETAPP_SVM_MGMT_IP = "192.168.1.223"
LAB_NETAPP_NFS_LIF_IPS = (
    "192.168.1.230",
    "192.168.1.231",
)
LAB_NETAPP_ISCSI_LIF_IPS = (
    "192.168.1.240",
    "192.168.1.241",
    "192.168.1.242",
    "192.168.1.243",
)


def _load_local_real_lab_env() -> None:
    candidates: list[Path] = []
    cwd = Path.cwd()
    repo_root = Path(__file__).resolve().parents[4]
    app_root = repo_root / "app"
    backend_root = app_root / "backend"

    search_bases = (
        (cwd,)
        if os.getenv("INFRA_CONFIG_TEST_ISOLATE_REAL_LAB_ENV") == "1"
        else (cwd, cwd.parent, cwd.parent.parent, backend_root, app_root, repo_root)
    )

    for base in search_bases:
        env_file = base / ".env.local.real-lab"
        if env_file not in candidates:
            candidates.append(env_file)

    for env_file in candidates:
        if path_exists(env_file):
            try:
                values = dotenv_values(env_file)
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            authoritative_real_lab = values.get("LAB_ENVIRONMENT") == "isolated-real-lab"
            for key, value in values.items():
                if key == "PROVIDER_MODE" or value is None:
                    continue
                if authoritative_real_lab:
                    os.environ[key] = value
                    continue
                existing = os.environ.get(key)
                if existing is not None:
                    if _is_stale_lab_ip(existing) and not _is_stale_lab_ip(value):
                        os.environ[key] = value
                    continue
                os.environ[key] = value
            if authoritative_real_lab:
                break


def _split_csv(value: str) -> list[str]:
    values: list[str] = []
    for item in value.split(","):
        cleaned = item.strip().strip("\"'")
        if cleaned and cleaned not in values:
            values.append(cleaned)
    return values


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


def _lab_default_env(name: str, default: str) -> str:
    value = _optional_env(name)
    if value is None or _is_stale_lab_ip(value):
        return default
    return value


def _lab_default_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _optional_env(name)
    if value is None or _is_stale_lab_ip(value):
        return default
    return tuple(_split_csv(value))


def _cisco_management_prefix() -> str:
    value = _optional_env("CISCO_MANAGEMENT_PREFIX")
    if value is None:
        return "/24"
    return "/24" if value == "255.255.255.0" else value


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


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
    esxi_license_key: str | None = _optional_env("ESXI_LICENSE_KEY")
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
    netapp_controller_a_sp: str = _lab_default_env(
        "NETAPP_CONTROLLER_A_SP",
        LAB_NETAPP_CONTROLLER_A_SP_IP,
    )
    netapp_controller_b_sp: str = _lab_default_env(
        "NETAPP_CONTROLLER_B_SP",
        LAB_NETAPP_CONTROLLER_B_SP_IP,
    )
    netapp_cluster_mgmt_ip: str = _lab_default_env(
        "NETAPP_CLUSTER_MGMT_IP",
        LAB_NETAPP_CLUSTER_MGMT_IP,
    )
    netapp_node_a_mgmt_ip: str = _lab_default_env(
        "NETAPP_NODE_A_MGMT_IP",
        LAB_NETAPP_NODE_A_MGMT_IP,
    )
    netapp_node_b_mgmt_ip: str = _lab_default_env(
        "NETAPP_NODE_B_MGMT_IP",
        LAB_NETAPP_NODE_B_MGMT_IP,
    )
    netapp_svm_mgmt_ip: str = _lab_default_env(
        "NETAPP_SVM_MGMT_IP",
        LAB_NETAPP_SVM_MGMT_IP,
    )
    netapp_iscsi_lifs: tuple[str, ...] = _lab_default_csv_env(
        "NETAPP_ISCSI_LIFS",
        LAB_NETAPP_ISCSI_LIF_IPS,
    )
    netapp_api_username: str | None = _optional_env("NETAPP_API_USERNAME")
    netapp_api_password: str | None = _optional_env("NETAPP_API_PASSWORD")
    netapp_api_verify_tls: bool = _bool_env("NETAPP_API_VERIFY_TLS", True)
    netapp_current_ontap_version: str | None = _optional_env("NETAPP_CURRENT_ONTAP_VERSION")
    netapp_license_keys: tuple[str, ...] = tuple(_split_csv(os.getenv("NETAPP_LICENSE_KEYS", "")))
    netapp_license_keys_file: str | None = _optional_env("NETAPP_LICENSE_KEYS_FILE")
    netapp_console_port: str | None = _optional_env("NETAPP_CONSOLE_PORT")
    netapp_console_baud: int = _int_env("NETAPP_CONSOLE_BAUD", 115200)
    netapp_console_timeout_seconds: float = _float_env("NETAPP_CONSOLE_TIMEOUT_SECONDS", 2.0)
    netapp_console_autodiscovery_disabled: bool = _bool_env("NETAPP_CONSOLE_AUTODISCOVERY_DISABLED", False)
    netapp_connected_management_ports: tuple[str, ...] = tuple(
        _split_csv(os.getenv("NETAPP_CONNECTED_MANAGEMENT_PORTS", "cluster_mgmt"))
    )
    netapp_management_topology_note: str = os.getenv(
        "NETAPP_MANAGEMENT_TOPOLOGY_NOTE",
        "Only one NetApp management port is connected at the moment.",
    )
    netapp_storage_protocol: str = os.getenv("NETAPP_STORAGE_PROTOCOL", "nfs")
    netapp_nfs_lifs: tuple[str, ...] = _lab_default_csv_env(
        "NETAPP_NFS_LIFS",
        LAB_NETAPP_NFS_LIF_IPS,
    )
    netapp_nfs_volume: str = os.getenv("NETAPP_NFS_VOLUME", "esxi_datastore_01")
    netapp_nfs_export_policy: str = os.getenv("NETAPP_NFS_EXPORT_POLICY", "esxi_nfs_policy")
    netapp_nfs_mount_path: str = os.getenv("NETAPP_NFS_MOUNT_PATH", "/esxi_datastore_01")
    netapp_nfs_datastore_name: str = os.getenv("NETAPP_NFS_DATASTORE_NAME", "netapp_nfs_ds01")
    netapp_nfs_client_match: str = os.getenv("NETAPP_NFS_CLIENT_MATCH", LAB_SUBNET_CIDR)
    netapp_cluster_name: str | None = _optional_env("NETAPP_CLUSTER_NAME")
    netapp_node_a_name: str | None = _optional_env("NETAPP_NODE_A_NAME")
    netapp_node_b_name: str | None = _optional_env("NETAPP_NODE_B_NAME")
    netapp_svm_name: str | None = _optional_env("NETAPP_SVM_NAME")
    netapp_dns_servers: tuple[str, ...] = tuple(_split_csv(os.getenv("NETAPP_DNS_SERVERS", "")))
    netapp_ntp_servers: tuple[str, ...] = tuple(_split_csv(os.getenv("NETAPP_NTP_SERVERS", "")))
    netapp_search_domains: tuple[str, ...] = tuple(_split_csv(os.getenv("NETAPP_SEARCH_DOMAINS", "")))
    netapp_admin_access_source: str | None = _optional_env("NETAPP_ADMIN_ACCESS_SOURCE")
    netapp_target_ontap_version: str | None = _optional_env("NETAPP_TARGET_ONTAP_VERSION")
    netapp_ontap_image_id: str | None = _optional_env("NETAPP_ONTAP_IMAGE_ID")
    netapp_upgrade_advisor_plan: str | None = _optional_env("NETAPP_UPGRADE_ADVISOR_PLAN")
    vcenter_configured: bool = _bool_env("VCENTER_CONFIGURED", False)
    vcenter_host: str | None = _optional_env("VCENTER_HOST") or _optional_env("GOVC_URL")
    vcenter_username: str | None = _optional_env("VCENTER_USERNAME") or _optional_env("GOVC_USERNAME")
    vcenter_password: str | None = _optional_env("VCENTER_PASSWORD") or _optional_env("GOVC_PASSWORD")
    vcenter_license_key: str | None = _optional_env("VCENTER_LICENSE_KEY")
    vcenter_verify_tls: bool = _bool_env("VCENTER_VERIFY_TLS", _bool_env("GOVC_TLS_VERIFY", True))
    vcenter_appliance_name: str | None = _optional_env("VCENTER_APPLIANCE_NAME")
    vcenter_management_ip: str | None = _optional_env("VCENTER_MANAGEMENT_IP")
    vcenter_subnet_cidr: str | None = _optional_env("VCENTER_SUBNET_CIDR")
    vcenter_gateway: str | None = _optional_env("VCENTER_GATEWAY")
    vcenter_dns_servers: tuple[str, ...] = tuple(_split_csv(os.getenv("VCENTER_DNS_SERVERS", "")))
    vcenter_ntp_servers: tuple[str, ...] = tuple(_split_csv(os.getenv("VCENTER_NTP_SERVERS", "")))
    vcenter_sso_domain: str | None = _optional_env("VCENTER_SSO_DOMAIN")
    vcenter_sso_admin_username: str | None = _optional_env("VCENTER_SSO_ADMIN_USERNAME")
    vcenter_sso_admin_password: str | None = _optional_env("VCENTER_SSO_ADMIN_PASSWORD")
    vcenter_appliance_root_password: str | None = _optional_env("VCENTER_APPLIANCE_ROOT_PASSWORD")
    vcenter_esxi_target: str | None = _optional_env("VCENTER_ESXI_TARGET")
    vcenter_datastore_target: str | None = _optional_env("VCENTER_DATASTORE_TARGET")
    vcenter_datacenter_name: str = os.getenv("VCENTER_DATACENTER_NAME", "Lab-DC")
    vcenter_cluster_name: str = os.getenv("VCENTER_CLUSTER_NAME", "Lab-Cluster")
    vcenter_vcsa_iso_path: str | None = _optional_env("VCENTER_VCSA_ISO_PATH") or _optional_env("VCSA_ISO_PATH")
    vcenter_vcsa_deploy_path: str | None = (
        _optional_env("VCENTER_VCSA_DEPLOY") or _optional_env("VCSA_DEPLOY_PATH") or _optional_env("VCSA_DEPLOY")
    )
    vcenter_deployment_size: str | None = _optional_env("VCENTER_DEPLOYMENT_SIZE") or "tiny"
    vcenter_network: str | None = _optional_env("VCENTER_NETWORK")
    vcenter_portgroup: str | None = _optional_env("VCENTER_PORTGROUP")
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
