"""The finder classifies devices only by what they say about themselves; nothing is contacted here."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finder  # noqa: E402

ILO_ROOT = '{"@odata.id":"/redfish/v1/","Vendor":"HPE","Product":"ProLiant DL360 Gen10","Oem":{"Hpe":{"Manager":[{"ManagerType":"iLO 5"}]}}}'
ESXI_PAGE = "<html><title>VMware ESXi</title><body>Welcome</body></html>"


def test_classification_from_self_descriptions():
    assert finder.classify((200, ILO_ROOT), (0, ""), "", None) == ("ilo", "HPE iLO · ProLiant DL360 Gen10")
    assert finder.classify((401, ""), (200, ESXI_PAGE), "", None) == ("esxi", "VMware ESXi")
    assert finder.classify((0, ""), (0, ""), "SSH-2.0-Cisco-1.25", None) == ("switch", "Cisco switch (SSH)")
    assert finder.classify((0, ""), (0, ""), "", "80:30:e0:30:bc:f2")[0] == "hpe"
    assert finder.classify((0, ""), (0, ""), "", "00:50:56:aa:bb:cc")[0] == "vm"
    assert finder.classify((0, ""), (0, ""), "", "aa:bb:cc:dd:ee:ff") == ("other", "Answers to ping; not identified")


def test_neighbour_table_parsing(monkeypatch):
    sample = "Interface: 192.0.2.19 --- 0x14\n  Internet Address      Physical Address      Type\n  192.0.2.27           80-30-e0-30-bc-f2     dynamic\n  192.0.2.31           ff-ff-ff-ff-ff-ff     static\n  224.0.0.22            01-00-5e-00-00-16     static\n"
    monkeypatch.setattr(finder.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": sample, "returncode": 0})())
    assert finder.neighbours() == {"192.0.2.27": "80:30:e0:30:bc:f2"}


def test_find_pings_the_subnet_then_asks_each_responder_and_sorts_ilo_first():
    pinged = []
    answered = {"192.0.2.27", "192.0.2.5", "192.0.2.9"}
    macs = {"192.0.2.27": "80:30:e0:30:bc:f2", "192.0.2.5": "20:67:7c:ef:92:b5", "192.0.2.9": "10:e7:c6:a9:56:33"}
    kinds = {"192.0.2.27": ("ilo", "HPE iLO · ProLiant DL360 Gen10"), "192.0.2.5": ("esxi", "VMware ESXi"), "192.0.2.9": ("other", "?")}
    found = finder.find("192.0.2.0/27", exclude={"192.0.2.19"}, pinger=lambda ip: (pinged.append(ip), ip in answered)[1], table=lambda: macs,
                        identifier=lambda ip, mac: {"ip": ip, "mac": mac, "kind": kinds[ip][0], "detail": kinds[ip][1]})
    assert len(pinged) == 30 and [f["ip"] for f in found] == ["192.0.2.27", "192.0.2.5", "192.0.2.9"]
    assert finder.find_mac("192.0.2.0/27", "20-67-7C-EF-92-B5", pinger=lambda ip: ip in answered, table=lambda: macs,
                           identifier=lambda ip, mac: {"ip": ip, "mac": mac, "kind": "x", "detail": ""}) == "192.0.2.5"


def test_my_networks_from_ipconfig():
    sample = ("Windows IP Configuration\n\nEthernet adapter Ethernet:\n\n   DHCP Enabled. . . . . . . . . . . : Yes\n   IPv4 Address. . . . . . . . . . . : 192.0.2.19(Preferred)\n"
              "   Subnet Mask . . . . . . . . . . . : 255.255.255.224\n   Default Gateway . . . . . . . . . : 192.0.2.1\n   DNS Servers . . . . . . . . . . . : 192.0.2.53\n"
              "                                       192.0.2.54\n\nWireless LAN adapter Wi-Fi:\n\n   DHCP Enabled. . . . . . . . . . . : Yes\n   IPv4 Address. . . . . . . . . . . : 198.51.100.7(Preferred)\n"
              "   Subnet Mask . . . . . . . . . . . : 255.255.255.0\n   Default Gateway . . . . . . . . . : 198.51.100.1\n\nEthernet adapter vEthernet (Default Switch):\n\n   IPv4 Address. . . . . . . . . . . : 172.16.0.1(Preferred)\n   Subnet Mask . . . . . . . . . . . : 255.255.240.0\n")
    nets = finder.parse_ipconfig(sample)
    assert [n["subnet"] for n in nets] == ["192.0.2.0/27", "198.51.100.0/24"]
    assert nets[0] == {"adapter": "Ethernet", "ip": "192.0.2.19", "subnet": "192.0.2.0/27", "gateway": "192.0.2.1", "dns": ["192.0.2.53", "192.0.2.54"], "dhcp": True, "wired": True}
