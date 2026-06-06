#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "This writes local real-lab settings to .env.local.real-lab."
echo "This file is ignored by Git and must never be committed."
echo "Lab IP profile: iLO .201, server NIC .202, ESXi .203, Cisco .204, Ansible/control host .205 on 192.168.1.0/24."
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

default_ilo_host="192.168.1.201"
default_server_embedded_nic_ip="192.168.1.202"
default_esxi_host="192.168.1.203"
default_cisco_ip="192.168.1.204"
default_ansible_control_host="192.168.1.205"

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

if [[ "${esxi_configured}" == "true" && -z "${esxi_host}" ]]; then
  echo "Aborted. ESXi configured probes require an ESXi host or lab IP."
  exit 1
fi

if [[ "${cisco_mgmt_configured}" == "true" && -z "${cisco_ip}" ]]; then
  echo "Aborted. Cisco management probes require a management host or lab IP."
  exit 1
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

LAB_SUBNET_CIDR=192.168.1.0/24
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
ENV

chmod 600 .env.local.real-lab

echo
echo "Wrote .env.local.real-lab"
echo "Provider mode: local-lab-readwrite"
echo "Destructive/rebuild mode: ${destructive_ack:-disabled}"
echo "Lab IP profile: iLO ${ilo_host}, server NIC ${server_embedded_nic_ip}, ESXi ${esxi_host}, Cisco ${cisco_ip}, Ansible/control ${ansible_control_host}"
echo "ESXi configured for probes: ${esxi_configured}"
echo "Cisco management configured for probes: ${cisco_mgmt_configured}"
