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

read -rp "iLO host or lab IP: " ilo_host

read -rp "Planned ESXi host or lab IP (optional): " esxi_host
read -rp "Is ESXi management configured for read-only probes? Type YES or press Enter: " esxi_ready

read -rp "Planned Cisco management host or lab IP after bootstrap (optional): " cisco_ip
read -rp "Is Cisco management IP/SSH configured? Type YES or press Enter: " cisco_ready

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
PROVIDER_MODE=local-readonly

LAB_CLOSED_LOOP_ACK=YES
LAB_READONLY_ACK=YES
LAB_DESTRUCTIVE_ACK=${destructive_ack}

LAB_USERNAME=${lab_user}
LAB_PASSWORD=${lab_password}

ILO_TEST_HOST=${ilo_host}
ILO_TEST_USERNAME=${lab_user}
ILO_TEST_PASSWORD=${lab_password}
ILO_TEST_VERIFY_TLS=false

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
ANSIBLE_CISCO_USERNAME=${lab_user}
ANSIBLE_CISCO_PASSWORD=${lab_password}
ANSIBLE_CISCO_ENABLE_PASSWORD=${lab_password}
ANSIBLE_CISCO_NETWORK_OS=cisco.ios.ios
ANSIBLE_CISCO_CONNECTION=ansible.netcommon.network_cli
ENV

chmod 600 .env.local.real-lab

echo
echo "Wrote .env.local.real-lab"
echo "Destructive/rebuild mode: ${destructive_ack:-disabled}"
echo "ESXi configured for probes: ${esxi_configured}"
echo "Cisco management configured for probes: ${cisco_mgmt_configured}"
