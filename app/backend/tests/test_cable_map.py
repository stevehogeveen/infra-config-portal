from app.services import cable_map

MAC_TABLE = """          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
 All    0100.0ccc.cccc    STATIC      CPU
 100    a0b1.c2d3.e401    DYNAMIC     Gi1/0/12
   1    a0b1.c2d3.e4ff    DYNAMIC     Gi1/0/13
   1    0011.2233.4455    DYNAMIC     Gi1/0/48
Total Mac Addresses for this criterion: 4
"""
STATUS = """Port         Name               Status       Vlan       Duplex  Speed Type
Gi1/0/12                        connected    100        a-full a-1000 10/100/1000BaseTX
Gi1/0/13                        connected    1          a-full a-1000 10/100/1000BaseTX
Gi1/0/48                        connected    trunk      a-full a-1000 10/100/1000BaseTX
Gi1/0/1                         notconnect   1            auto   auto 10/100/1000BaseTX
"""


def test_parse_and_match():
    assert cable_map.parse_mac_table(MAC_TABLE)["a0:b1:c2:d3:e4:01"] == {"port": "Gi1/0/12", "vlan": "100"}
    servers = {"srv": [{"mac": "a0:b1:c2:d3:e4:01", "label": "vmnic1 (LOM port 2)", "link": True},
                       {"mac": "a0:b1:c2:d3:e4:ff", "label": "iLO port", "link": None},
                       {"mac": "a0:b1:c2:d3:e4:02", "label": "vmnic0 (LOM port 1)", "link": True}]}
    result = cable_map.build(servers, {"sw": {"show mac address-table": MAC_TABLE, "show interfaces status": STATUS}},
                             {"srv": "HPE DL360 1", "sw": "Cisco switch 1"})
    assert [(c["server_port"], c["switch_port"], c["vlan"]) for c in result["cables"]] == [("vmnic1 (LOM port 2)", "Gi1/0/12", "100"), ("iLO port", "Gi1/0/13", "1")]
    assert [p["server_port"] for p in result["unmatched_server_ports"]] == ["vmnic0 (LOM port 1)"]
    assert [p["switch_port"] for p in result["other_switch_ports"]] == ["Gi1/0/48"]
