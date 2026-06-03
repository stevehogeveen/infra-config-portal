#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "This writes local real-lab settings to .env.local.real-lab."
echo "This file is ignored by Git and must never be committed."
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

read -rp "iLO host [192.168.1.200]: " ilo_host
ilo_host="${ilo_host:-192.168.1.200}"

read -rp "ESXi host [192.168.1.210]: " esxi_host
esxi_host="${esxi_host:-192.168.1.210}"

read -rp "Cisco target management IP after bootstrap [192.168.1.220]: " cisco_ip
cisco_ip="${cisco_ip:-192.168.1.220}"

read -rp "Lab username [admin]: " lab_user
lab_user="${lab_user:-admin}"

read -rsp "Lab password: " lab_password
echo

read -rp "Cisco console baud [9600]: " cisco_baud
cisco_baud="${cisco_baud:-9600}"

cat > .env.local.real-lab <<ENV
# Local real-lab settings. Do not commit.
PROVIDER_MODE=local-readonly

LAB_CLOSED_LOOP_ACK=YES
LAB_READONLY_ACK=YES
LAB_DESTRUCTIVE_ACK=${destructive_ack}

LAB_USERNAME=${lab_user}
LAB_PASSWORD=${lab_password}

ILO_TEST_HOST=${ilo_host}
ILO_TEST_USERNAME=${lab_user}
ILO_TEST_PASSWORD=${lab_password}
ILO_REDFISH_VERIFY_TLS=false

ESXI_TEST_HOST=${esxi_host}
ESXI_TEST_USERNAME=${lab_user}
ESXI_TEST_PASSWORD=${lab_password}

CISCO_TARGET_IP=${cisco_ip}
CISCO_TEST_USERNAME=${lab_user}
CISCO_TEST_PASSWORD=${lab_password}
CISCO_ENABLE_PASSWORD=${lab_password}
CISCO_CONSOLE_BAUD=${cisco_baud}

ANSIBLE_CISCO_HOST=${cisco_ip}
ANSIBLE_CISCO_USERNAME=${lab_user}
ANSIBLE_CISCO_PASSWORD=${lab_password}
ANSIBLE_CISCO_ENABLE_PASSWORD=${lab_password}
ANSIBLE_CISCO_NETWORK_OS=ios
ANSIBLE_CISCO_CONNECTION=network_cli
ENV

chmod 600 .env.local.real-lab

echo
echo "Wrote .env.local.real-lab"
echo "Destructive/rebuild mode: ${destructive_ack:-disabled}"
