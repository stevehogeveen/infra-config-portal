#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "This writes local real-lab settings to .env.local.real-lab."
echo "This file is ignored by Git and must never be committed."
echo "Saved lab profiles live under .local/ and are the app's address source."
echo ".env.local.real-lab is bootstrap/secrets/emergency override only."
echo "Reports and artifacts are evidence, not a configuration source."
echo

read -rp "Closed loop lab network only? Type YES: " closed_loop
if [[ "${closed_loop}" != "YES" ]]; then
  echo "Aborted. Real-lab testing requires closed-loop confirmation."
  exit 1
fi

read -rp "Allow read-only real device discovery? Type YES: " readonly_ack
if [[ "${readonly_ack}" != "YES" ]]; then
  echo "Aborted. Read-only discovery not confirmed."
  exit 1
fi

echo
echo "Destructive/rebuild actions are separate."
echo "Examples: Cisco bootstrap/config reset, ESXi rebuild/reinstall, firmware/upgrade workflows."
echo "Leave disabled unless you are ready for wipe/rebuild style testing."
read -rp "Allow destructive/rebuild lab actions? Type REBUILD_LAB or press Enter to keep disabled: " destructive_ack

echo
echo "local-lab-readwrite mode can contact and reconfigure isolated real lab equipment."
read -rp "Acknowledge real hardware? Type YES: " ack_real_hardware
read -rp "Acknowledge device reconfiguration? Type YES: " ack_device_reconfiguration
read -rp "Acknowledge data loss risk? Type YES: " ack_data_loss
read -rp "Acknowledge lab-only use? Type YES: " ack_lab_only

ip_to_int() {
  local IFS=.
  local a b c d
  read -r a b c d <<< "$1"
  echo $(( (a << 24) + (b << 16) + (c << 8) + d ))
}

int_to_ip() {
  local value=$1
  printf "%d.%d.%d.%d" \
    $(( (value >> 24) & 255 )) \
    $(( (value >> 16) & 255 )) \
    $(( (value >> 8) & 255 )) \
    $(( value & 255 ))
}

network_for_cidr() {
  local cidr=$1
  local ip=${cidr%/*}
  local prefix=${cidr##*/}
  local ip_int mask network_int
  ip_int=$(ip_to_int "${ip}")
  mask=$(( (0xffffffff << (32 - prefix)) & 0xffffffff ))
  network_int=$(( ip_int & mask ))
  echo "$(int_to_ip "${network_int}")/${prefix}"
}

address_at_offset() {
  local network_ip=$1
  local offset=$2
  local network_int
  network_int=$(ip_to_int "${network_ip}")
  int_to_ip $(( network_int + offset ))
}

read -rp "Lab subnet CIDR [192.168.1.0/24]: " lab_subnet_cidr
lab_subnet_cidr="${lab_subnet_cidr:-192.168.1.0/24}"
lab_subnet_cidr="$(network_for_cidr "${lab_subnet_cidr}")"
lab_subnet_prefix="${lab_subnet_cidr##*/}"
lab_subnet_network="${lab_subnet_cidr%/*}"

default_profile_topology="compact_edge_lab"
if (( lab_subnet_prefix <= 24 )); then
  default_profile_topology="high_address_lab"
fi

echo
echo "Detected ${lab_subnet_cidr}; default topology is ${default_profile_topology}."
echo "high_address_lab uses /24-style .201/.202/.203/.204/.205 and NetApp .210/.211/.220+."
echo "compact_edge_lab uses gateway +1, switch +2/+3, UPS +7, backup +8, utility VM +9, ESXi +10, iLO +11."
read -rp "Profile topology [${default_profile_topology}]: " profile_topology
profile_topology="${profile_topology:-$default_profile_topology}"

if [[ "${profile_topology}" == "compact_edge_lab" ]]; then
  default_gateway="$(address_at_offset "${lab_subnet_network}" 1)"
  default_cisco_ip="$(address_at_offset "${lab_subnet_network}" 2)"
  default_ansible_control_host="$(address_at_offset "${lab_subnet_network}" 9)"
  default_esxi_host="$(address_at_offset "${lab_subnet_network}" 10)"
  default_ilo_host="$(address_at_offset "${lab_subnet_network}" 11)"
  default_server_embedded_nic_ip=""
  netapp_in_scope=false
  echo "Compact topology disables NetApp and vCenter by default; they are not normal validation blockers."
  read -rp "Manually include NetApp/vCenter bootstrap fields anyway? Type INCLUDE_NETAPP or press Enter: " include_netapp_ack
  if [[ "${include_netapp_ack}" == "INCLUDE_NETAPP" ]]; then
    netapp_in_scope=true
  fi
else
  default_gateway="$(address_at_offset "${lab_subnet_network}" 1)"
  default_ilo_host="$(address_at_offset "${lab_subnet_network}" 201)"
  default_server_embedded_nic_ip="$(address_at_offset "${lab_subnet_network}" 202)"
  default_esxi_host="$(address_at_offset "${lab_subnet_network}" 203)"
  default_cisco_ip="$(address_at_offset "${lab_subnet_network}" 204)"
  default_ansible_control_host="$(address_at_offset "${lab_subnet_network}" 205)"
  netapp_in_scope=true
  read -rp "Include NetApp bootstrap fields for this high-address profile? Type NO to skip [YES]: " include_netapp_ack
  if [[ "${include_netapp_ack}" == "NO" ]]; then
    netapp_in_scope=false
  fi
fi

default_netapp_controller_a_sp=""
default_netapp_controller_b_sp=""
default_netapp_cluster_mgmt_ip=""
default_netapp_node_a_mgmt_ip=""
default_netapp_node_b_mgmt_ip=""
default_netapp_svm_mgmt_ip=""
default_netapp_iscsi_lifs=""
default_netapp_nfs_lifs=""
if [[ "${netapp_in_scope}" == "true" && "${lab_subnet_prefix}" -le 24 ]]; then
  default_netapp_controller_a_sp="$(address_at_offset "${lab_subnet_network}" 210)"
  default_netapp_controller_b_sp="$(address_at_offset "${lab_subnet_network}" 211)"
  default_netapp_cluster_mgmt_ip="$(address_at_offset "${lab_subnet_network}" 220)"
  default_netapp_node_a_mgmt_ip="$(address_at_offset "${lab_subnet_network}" 221)"
  default_netapp_node_b_mgmt_ip="$(address_at_offset "${lab_subnet_network}" 222)"
  default_netapp_svm_mgmt_ip="$(address_at_offset "${lab_subnet_network}" 223)"
  default_netapp_iscsi_lifs="$(address_at_offset "${lab_subnet_network}" 240),$(address_at_offset "${lab_subnet_network}" 241),$(address_at_offset "${lab_subnet_network}" 242),$(address_at_offset "${lab_subnet_network}" 243)"
  default_netapp_nfs_lifs="$(address_at_offset "${lab_subnet_network}" 230),$(address_at_offset "${lab_subnet_network}" 231)"
elif [[ "${netapp_in_scope}" == "true" ]]; then
  echo "Manual NetApp opt-in on compact topology requires custom in-subnet addresses; no high-address defaults will be generated."
fi
default_netapp_nfs_volume="esxi_datastore_01"
default_netapp_nfs_export_policy="esxi_nfs_policy"
default_netapp_nfs_mount_path="/esxi_datastore_01"
default_netapp_nfs_datastore_name="netapp_nfs_ds01"

echo
echo "Derived bootstrap defaults:"
echo "  gateway ${default_gateway}"
echo "  Cisco/switch ${default_cisco_ip}"
echo "  control/utility ${default_ansible_control_host}"
echo "  ESXi ${default_esxi_host}"
echo "  iLO ${default_ilo_host}"
if [[ "${netapp_in_scope}" == "true" ]]; then
  echo "  NetApp cluster ${default_netapp_cluster_mgmt_ip}"
else
  echo "  NetApp/vCenter not in scope"
fi

read -rp "iLO host or lab IP [${default_ilo_host}]: " ilo_host
ilo_host="${ilo_host:-$default_ilo_host}"

read -rp "Server embedded NIC IP [${default_server_embedded_nic_ip}]: " server_embedded_nic_ip
server_embedded_nic_ip="${server_embedded_nic_ip:-$default_server_embedded_nic_ip}"

read -rp "Planned ESXi management IP [${default_esxi_host}]: " esxi_host
esxi_host="${esxi_host:-$default_esxi_host}"
read -rp "Is ESXi management configured for read-only probes? Type YES or press Enter: " esxi_ready

read -rp "Planned Cisco management IP after console bootstrap [${default_cisco_ip}]: " cisco_ip
cisco_ip="${cisco_ip:-$default_cisco_ip}"
read -rp "Is Cisco management IP/SSH configured? Type YES or press Enter: " cisco_ready

read -rp "Ansible/control host IP [${default_ansible_control_host}]: " ansible_control_host
ansible_control_host="${ansible_control_host:-$default_ansible_control_host}"

netapp_controller_a_sp=""
netapp_controller_b_sp=""
netapp_cluster_mgmt_ip=""
netapp_node_a_mgmt_ip=""
netapp_node_b_mgmt_ip=""
netapp_svm_mgmt_ip=""
netapp_iscsi_lifs=""
netapp_console_port=""
netapp_console_baud="115200"
netapp_connected_management_ports=""
netapp_nfs_lifs=""
netapp_nfs_volume=""
netapp_nfs_export_policy=""
netapp_nfs_mount_path=""
netapp_nfs_datastore_name=""
netapp_ready=""
vcenter_ready=""
vcenter_host=""

if [[ "${netapp_in_scope}" == "true" ]]; then
  echo
  echo "NetApp is added as planned targets only by default."
  read -rp "Controller A SP IP [${default_netapp_controller_a_sp}]: " netapp_controller_a_sp
  netapp_controller_a_sp="${netapp_controller_a_sp:-$default_netapp_controller_a_sp}"
  read -rp "Controller B SP IP [${default_netapp_controller_b_sp}]: " netapp_controller_b_sp
  netapp_controller_b_sp="${netapp_controller_b_sp:-$default_netapp_controller_b_sp}"
  read -rp "Planned NetApp cluster management IP [${default_netapp_cluster_mgmt_ip}]: " netapp_cluster_mgmt_ip
  netapp_cluster_mgmt_ip="${netapp_cluster_mgmt_ip:-$default_netapp_cluster_mgmt_ip}"
  read -rp "Planned NetApp Node A management/e0M IP [${default_netapp_node_a_mgmt_ip}]: " netapp_node_a_mgmt_ip
  netapp_node_a_mgmt_ip="${netapp_node_a_mgmt_ip:-$default_netapp_node_a_mgmt_ip}"
  read -rp "Planned NetApp Node B management/e0M IP [${default_netapp_node_b_mgmt_ip}]: " netapp_node_b_mgmt_ip
  netapp_node_b_mgmt_ip="${netapp_node_b_mgmt_ip:-$default_netapp_node_b_mgmt_ip}"
  read -rp "Planned NetApp SVM management IP [${default_netapp_svm_mgmt_ip}]: " netapp_svm_mgmt_ip
  netapp_svm_mgmt_ip="${netapp_svm_mgmt_ip:-$default_netapp_svm_mgmt_ip}"
  read -rp "Planned NetApp iSCSI LIFs comma-separated [${default_netapp_iscsi_lifs}]: " netapp_iscsi_lifs
  netapp_iscsi_lifs="${netapp_iscsi_lifs:-$default_netapp_iscsi_lifs}"
  read -rp "Optional NetApp console port hint, blank for auto-discovery []: " netapp_console_port
  read -rp "NetApp console baud [115200]: " netapp_console_baud
  netapp_console_baud="${netapp_console_baud:-115200}"
  read -rp "Connected NetApp management ports comma-separated [cluster_mgmt]: " netapp_connected_management_ports
  netapp_connected_management_ports="${netapp_connected_management_ports:-cluster_mgmt}"
  read -rp "Planned NetApp NFS LIFs comma-separated [${default_netapp_nfs_lifs}]: " netapp_nfs_lifs
  netapp_nfs_lifs="${netapp_nfs_lifs:-$default_netapp_nfs_lifs}"
  read -rp "Planned NetApp NFS volume [${default_netapp_nfs_volume}]: " netapp_nfs_volume
  netapp_nfs_volume="${netapp_nfs_volume:-$default_netapp_nfs_volume}"
  read -rp "Planned NetApp export policy [${default_netapp_nfs_export_policy}]: " netapp_nfs_export_policy
  netapp_nfs_export_policy="${netapp_nfs_export_policy:-$default_netapp_nfs_export_policy}"
  read -rp "Planned NetApp NFS mount path [${default_netapp_nfs_mount_path}]: " netapp_nfs_mount_path
  netapp_nfs_mount_path="${netapp_nfs_mount_path:-$default_netapp_nfs_mount_path}"
  read -rp "Planned vCenter/ESXi datastore name [${default_netapp_nfs_datastore_name}]: " netapp_nfs_datastore_name
  netapp_nfs_datastore_name="${netapp_nfs_datastore_name:-$default_netapp_nfs_datastore_name}"
  read -rp "Legacy NetApp API configured hint, optional because live validation derives state. Type YES or press Enter: " netapp_ready
  read -rp "Is vCenter/govc configured for datastore validation? Type YES or press Enter: " vcenter_ready
  read -rp "vCenter host or GOVC_URL, blank if not ready []: " vcenter_host
else
  echo
  echo "NetApp and vCenter prompts skipped: ${profile_topology} marks them not_in_scope by default."
fi

if [[ -z "${ilo_host}" ]]; then
  echo "Aborted. iLO is the only required configured real-lab network target."
  exit 1
fi

esxi_configured=false
if [[ "${esxi_ready}" == "YES" ]]; then
  esxi_configured=true
fi

cisco_mgmt_configured=false
if [[ "${cisco_ready}" == "YES" ]]; then
  cisco_mgmt_configured=true
fi

netapp_configured=false
if [[ "${netapp_ready}" == "YES" ]]; then
  netapp_configured=true
fi

vcenter_configured=false
if [[ "${vcenter_ready}" == "YES" ]]; then
  vcenter_configured=true
fi

if [[ "${esxi_configured}" == "true" && -z "${esxi_host}" ]]; then
  echo "Aborted. ESXi configured probes require an ESXi host or lab IP."
  exit 1
fi

if [[ "${cisco_mgmt_configured}" == "true" && -z "${cisco_ip}" ]]; then
  echo "Aborted. Cisco management probes require a management host or lab IP."
  exit 1
fi

if [[ "${netapp_configured}" == "true" && -z "${netapp_cluster_mgmt_ip}" ]]; then
  echo "Aborted. NetApp configured probes require a cluster management IP."
  exit 1
fi

if [[ "${vcenter_configured}" == "true" && -z "${vcenter_host}" ]]; then
  echo "Aborted. vCenter configured validation requires VCENTER_HOST or GOVC_URL."
  exit 1
fi

storage_protocol="none"
if [[ "${netapp_in_scope}" == "true" ]]; then
  storage_protocol="nfs"
fi

read -rp "Lab username [admin]: " lab_user
lab_user="${lab_user:-admin}"

read -rsp "Lab password: " lab_password
echo

read -rp "Cisco console baud [9600]: " cisco_baud
cisco_baud="${cisco_baud:-9600}"

cat > .env.local.real-lab <<ENV
# Local real-lab settings. Do not commit.
PROVIDER_MODE=local-lab-readwrite

LAB_PROFILE_TOPOLOGY=${profile_topology}
LAB_PROFILE_NETAPP_ENABLED=${netapp_in_scope}
LAB_CLOSED_LOOP_ACK=YES
LAB_READONLY_ACK=YES
LAB_DESTRUCTIVE_ACK=${destructive_ack}

LAB_ENVIRONMENT=isolated-real-lab
LAB_ACKNOWLEDGE_REAL_HARDWARE=$([[ "${ack_real_hardware}" == "YES" ]] && echo true || echo false)
LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=$([[ "${ack_device_reconfiguration}" == "YES" ]] && echo true || echo false)
LAB_ACKNOWLEDGE_DATA_LOSS_RISK=$([[ "${ack_data_loss}" == "YES" ]] && echo true || echo false)
LAB_ACKNOWLEDGE_LAB_ONLY=$([[ "${ack_lab_only}" == "YES" ]] && echo true || echo false)
LAB_ALLOW_POWER_ACTIONS=false
LAB_ALLOW_FIRMWARE_UPDATES=false
LAB_ALLOW_FACTORY_RESET=false

LAB_USERNAME=${lab_user}
LAB_PASSWORD=${lab_password}

LAB_SUBNET_CIDR=${lab_subnet_cidr}
LAB_GATEWAY=${default_gateway}
SERVER_EMBEDDED_NIC_IP=${server_embedded_nic_ip}

ILO_TEST_HOST=${ilo_host}
ILO_TEST_USERNAME=${lab_user}
ILO_TEST_PASSWORD=${lab_password}
ILO_TEST_VERIFY_TLS=false
ILO_SETUP_APPLY_ENABLED=false

ESXI_CONFIGURED=${esxi_configured}
ESXI_TEST_HOST=${esxi_host}
ESXI_TEST_USERNAME=${lab_user}
ESXI_TEST_PASSWORD=${lab_password}
ESXI_TEST_VERIFY_TLS=false

CISCO_MGMT_CONFIGURED=${cisco_mgmt_configured}
CISCO_TARGET_IP=${cisco_ip}
CISCO_TEST_USERNAME=${lab_user}
CISCO_TEST_PASSWORD=${lab_password}
CISCO_ENABLE_PASSWORD=${lab_password}
CISCO_CONSOLE_BAUD=${cisco_baud}

ANSIBLE_CISCO_HOST=${cisco_ip}
ANSIBLE_CONTROL_HOST=${ansible_control_host}
ANSIBLE_CISCO_USERNAME=${lab_user}
ANSIBLE_CISCO_PASSWORD=${lab_password}
ANSIBLE_CISCO_ENABLE_PASSWORD=${lab_password}
ANSIBLE_CISCO_NETWORK_OS=cisco.ios.ios
ANSIBLE_CISCO_CONNECTION=ansible.netcommon.network_cli

NETAPP_CONFIGURED=${netapp_configured}
NETAPP_CONTROLLER_A_SP=${netapp_controller_a_sp}
NETAPP_CONTROLLER_B_SP=${netapp_controller_b_sp}
NETAPP_CLUSTER_MGMT_IP=${netapp_cluster_mgmt_ip}
NETAPP_NODE_A_MGMT_IP=${netapp_node_a_mgmt_ip}
NETAPP_NODE_B_MGMT_IP=${netapp_node_b_mgmt_ip}
NETAPP_SVM_MGMT_IP=${netapp_svm_mgmt_ip}
NETAPP_ISCSI_LIFS=${netapp_iscsi_lifs}
NETAPP_API_VERIFY_TLS=false
NETAPP_CONSOLE_PORT=${netapp_console_port}
NETAPP_CONSOLE_BAUD=${netapp_console_baud}
NETAPP_CONSOLE_TIMEOUT_SECONDS=2.0
NETAPP_CONNECTED_MANAGEMENT_PORTS=${netapp_connected_management_ports}
NETAPP_MANAGEMENT_TOPOLOGY_NOTE='Only one NetApp management port is connected at the moment.'
NETAPP_STORAGE_PROTOCOL=${storage_protocol}
NETAPP_NFS_LIFS=${netapp_nfs_lifs}
NETAPP_NFS_VOLUME=${netapp_nfs_volume}
NETAPP_NFS_EXPORT_POLICY=${netapp_nfs_export_policy}
NETAPP_NFS_MOUNT_PATH=${netapp_nfs_mount_path}
NETAPP_NFS_DATASTORE_NAME=${netapp_nfs_datastore_name}
NETAPP_NFS_CLIENT_MATCH=${lab_subnet_cidr}
VCENTER_CONFIGURED=${vcenter_configured}
VCENTER_HOST=${vcenter_host}
VCENTER_VERIFY_TLS=false
ENV

if [[ "${netapp_configured}" == "true" ]]; then
  {
    echo "NETAPP_API_USERNAME=${lab_user}"
    echo "NETAPP_API_PASSWORD=${lab_password}"
  } >> .env.local.real-lab
fi

if [[ "${vcenter_configured}" == "true" ]]; then
  {
    echo "VCENTER_USERNAME=${lab_user}"
    echo "VCENTER_PASSWORD=${lab_password}"
    echo "GOVC_URL=${vcenter_host}"
    echo "GOVC_USERNAME=${lab_user}"
    echo "GOVC_PASSWORD=${lab_password}"
    echo "GOVC_TLS_VERIFY=false"
  } >> .env.local.real-lab
fi

chmod 600 .env.local.real-lab

echo
echo "Wrote .env.local.real-lab"
echo "Provider mode: local-lab-readwrite"
echo "Destructive/rebuild mode: ${destructive_ack:-disabled}"
echo "Lab profile topology: ${profile_topology}"
echo "Lab subnet: ${lab_subnet_cidr}"
echo "Lab IP profile: iLO ${ilo_host}, server NIC ${server_embedded_nic_ip:-not_in_scope}, ESXi ${esxi_host}, Cisco ${cisco_ip}, Ansible/control ${ansible_control_host}, NetApp ${netapp_cluster_mgmt_ip:-not_in_scope}"
echo "ESXi configured for probes: ${esxi_configured}"
echo "Cisco management configured for probes: ${cisco_mgmt_configured}"
echo "NetApp configured for probes: ${netapp_configured}"
echo "vCenter/govc configured for validation: ${vcenter_configured}"
