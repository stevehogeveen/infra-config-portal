"""The finder: which devices are on the kit's network right now, and what are they?

Everything on a new kit starts on a DHCP address: the iLO, the switch once it is set up, ESXi when
planned that way. Nobody should have to go and read those addresses off a screen. The finder, on
an explicit click only, pings the kit's subnet from this PC, reads the PC's neighbour table for the
MAC address of everything that answered, and asks each one what it is, using only answers that
need no sign-in:
  iLO     - the Redfish service root (https://<ip>/redfish/v1/) names HPE and the server model
  ESXi    - the welcome page (https://<ip>/) says VMware ESXi
  switch  - the SSH banner (port 22) says Cisco
Nothing is changed anywhere. Results are suggestions; the operator chooses.
"""

from __future__ import annotations

import ipaddress
import json
import platform
import re
import socket
import ssl
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

# Well-known HPE/HP iLO and server NIC OUIs (a hint only; the Redfish answer decides).
HPE_OUIS = {"80:30:e0", "94:40:c9", "38:63:bb", "1c:98:ec", "5c:b9:01", "3c:a8:2a", "ec:eb:b8", "b4:7a:f1", "9c:dc:71", "30:e1:71", "fc:15:b4",
            "98:f2:b3", "48:df:37", "14:02:ec", "00:9c:02", "2c:44:fd", "e4:11:5b", "d0:bf:9c", "70:10:6f", "a0:d3:c1", "ac:16:2d", "c4:34:6b",
            "28:80:23", "3c:d9:2b", "6c:3b:e5", "8c:dc:d4", "f4:03:43", "b0:5a:da", "20:67:7c", "10:e7:c6", "b0:0c:d1", "28:c5:c8"}
VMWARE_OUIS = {"00:50:56", "00:0c:29", "00:05:69", "00:1c:14"}
ARP_ROW = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s", re.M)
INSECURE = ssl.create_default_context()
INSECURE.check_hostname = False
INSECURE.verify_mode = ssl.CERT_NONE  # new equipment has self-signed certificates; this only reads what it calls itself


def _mac(value: str) -> str:
    return value.lower().replace("-", ":")


def ping(ip: str, timeout_ms: int = 400) -> bool:
    flag = ["-n", "1", "-w", str(timeout_ms)] if platform.system() == "Windows" else ["-c", "1", "-W", str(max(1, timeout_ms // 1000))]
    try:
        return subprocess.run(["ping", *flag, ip], capture_output=True, timeout=timeout_ms / 1000 + 2, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def neighbours() -> dict[str, str]:
    """ip -> mac from the PC's neighbour (ARP) table."""
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return {ip: _mac(mac) for ip, mac in ARP_ROW.findall(out) if not _mac(mac).startswith(("ff:ff", "01:00:5e"))}


def _https(ip: str, path: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(f"https://{ip}{path}", headers={"Accept": "application/json, text/html"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=INSECURE) as response:
            return response.status, response.read(20000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(20000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - not answering is an answer
        return 0, ""


def _ssh_banner(ip: str, timeout: float) -> str:
    try:
        with socket.create_connection((ip, 22), timeout=timeout) as sock:
            sock.settimeout(timeout)
            return sock.recv(200).decode("utf-8", "replace").strip()
    except OSError:
        return ""


def classify(redfish: tuple[int, str], welcome: tuple[int, str], banner: str, mac: str | None) -> tuple[str, str]:
    """(kind, detail) from what a device said about itself. Pure; tested directly."""
    status, body = redfish
    if status == 200:
        try:
            root = json.loads(body)
        except ValueError:
            root = {}
        vendor = str(root.get("Vendor") or "")
        oem = root.get("Oem") or {}
        if "hpe" in vendor.lower() or "hp" == vendor.lower() or any(k.lower() in ("hpe", "hp") for k in oem):
            return "ilo", f"HPE iLO · {root.get('Product') or 'server'}"
        if vendor or root.get("RedfishVersion"):
            return "bmc", f"{vendor or 'Redfish'} management controller"
    if "vmware esxi" in welcome[1].lower() or "vmware" in welcome[1].lower() and "esxi" in welcome[1].lower():
        return "esxi", "VMware ESXi"
    if banner.lower().startswith("ssh-") and "cisco" in banner.lower():
        return "switch", "Cisco switch (SSH)"
    if banner.lower().startswith("ssh-"):
        return "ssh", f"Something with SSH ({banner[:40]})"
    prefix = (mac or "")[:8]
    if prefix in HPE_OUIS:
        return "hpe", "HPE hardware (by its MAC address); not answering on its web port"
    if prefix in VMWARE_OUIS:
        return "vm", "A virtual machine (VMware MAC address)"
    return "other", "Answers to ping; not identified"


def identify(ip: str, mac: str | None, timeout: float = 2.5) -> dict[str, Any]:
    kind, detail = classify(_https(ip, "/redfish/v1/", timeout), _https(ip, "/", timeout), _ssh_banner(ip, timeout), mac)
    return {"ip": ip, "mac": mac, "kind": kind, "detail": detail}


ORDER = {"ilo": 0, "esxi": 1, "switch": 2, "bmc": 3, "hpe": 4, "ssh": 5, "vm": 6, "other": 7}


def find(subnet: str, *, exclude: set[str] = frozenset(), pinger: Callable[[str], bool] = ping, table: Callable[[], dict[str, str]] = neighbours,
         identifier: Callable[[str, str | None], dict[str, Any]] = identify, limit: int = 1024) -> list[dict[str, Any]]:
    """Ping the subnet, collect who answered (and their MACs), ask each what it is. Read-only."""
    network = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(h) for h in network.hosts()][:limit]
    with ThreadPoolExecutor(max_workers=64) as pool:
        alive = {ip for ip, ok in zip(hosts, pool.map(pinger, hosts)) if ok and ip not in exclude}
    macs = table()
    alive |= {ip for ip in macs if ip not in exclude and ipaddress.ip_address(ip) in network}
    alive = {ip for ip in alive if not is_mine(ip)}
    with ThreadPoolExecutor(max_workers=32) as pool:
        found = list(pool.map(lambda ip: identifier(ip, macs.get(ip)), sorted(alive, key=lambda a: ipaddress.ip_address(a))))
    return sorted(found, key=lambda f: (ORDER.get(f["kind"], 9), ipaddress.ip_address(f["ip"])))


def find_mac(subnet: str, mac: str, **kw: Any) -> str | None:
    """The address a given MAC (say ESXi's management NIC) currently has on the subnet, or None."""
    wanted = _mac(mac)
    for device in find(subnet, **kw):
        if device.get("mac") == wanted:
            return device["ip"]
    return None


def my_networks() -> list[dict[str, Any]]:
    """The networks this PC is on right now, from its adapters: subnet, gateway, DNS, and whether DHCP gave it."""
    if platform.system() != "Windows":
        return []
    try:
        out = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_ipconfig(out)


def parse_ipconfig(out: str) -> list[dict[str, Any]]:
    nets: list[dict[str, Any]] = []
    for block in re.split(r"\r?\n(?=\S)", out):
        if not block.strip():
            continue
        name = block.splitlines()[0].strip().rstrip(":")
        ip = re.search(r"IPv4 Address[ .]*: ([\d.]+)", block)
        mask = re.search(r"Subnet Mask[ .]*: ([\d.]+)", block)
        if not ip or not mask or ip.group(1).startswith("169.254") or "vEthernet" in name or "Virtual" in name:
            continue
        gateway = re.search(r"Default Gateway[ .]*: ([\d.]+)", block)
        dns = re.findall(r"(?:DNS Servers[ .]*: |^\s{30,})([\d.]+)\s*$", block, re.M)
        dhcp = bool(re.search(r"DHCP Enabled[ .]*: Yes", block))
        network = ipaddress.ip_interface(f"{ip.group(1)}/{mask.group(1)}").network
        nets.append({"adapter": name.replace("Ethernet adapter ", "").replace("Wireless LAN adapter ", ""), "ip": ip.group(1), "subnet": str(network),
                     "gateway": gateway.group(1) if gateway else None, "dns": dns, "dhcp": dhcp, "wired": "Wi-Fi" not in name and "Wireless" not in name})
    return sorted(nets, key=lambda n: (not n["wired"], not n["dhcp"]))


def is_mine(ip: str) -> bool:
    """Only this PC can bind a socket to one of its own addresses (even on an unplugged adapter)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((ip, 0))
        return True
    except OSError:
        return False


def my_addresses() -> set[str]:
    """This PC's own IPv4 addresses, including adapters that are configured but not connected."""
    mine: set[str] = set()
    try:
        mine |= {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    try:
        command = ["ipconfig"] if platform.system() == "Windows" else ["ip", "-4", "-o", "addr"]
        out = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False).stdout
        mine |= set(re.findall(r"(?:IPv4 Address[^:\n]*:\s*|inet )(\d{1,3}(?:\.\d{1,3}){3})", out))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return mine
