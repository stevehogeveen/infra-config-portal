import json
from types import SimpleNamespace

import pytest

from app.providers import esxi_govc as govc


def test_password_travels_only_in_the_environment_and_is_masked_in_errors(monkeypatch):
    calls = []

    def fake_run(argv, env, **kwargs):
        calls.append((argv, env))
        return SimpleNamespace(returncode=1, stdout="", stderr="ServerFaultCode: failed with Fixture-Secret-1 in it")

    monkeypatch.setattr(govc.shutil, "which", lambda name: "/usr/local/bin/govc")
    monkeypatch.setattr(govc.subprocess, "run", fake_run)
    with pytest.raises(govc.GovcError) as raised:
        govc.run("192.0.2.20", "Fixture-Secret-1", "about", "-json")
    argv, env = calls[0]
    assert "Fixture-Secret-1" not in " ".join(argv)
    assert env["GOVC_PASSWORD"] == "Fixture-Secret-1" and env["GOVC_URL"] == "https://192.0.2.20/sdk"
    assert env["GOVC_USERNAME"] == "root" and env["GOVC_INSECURE"] == "1"
    assert "Fixture-Secret-1" not in str(raised.value)


def test_host_facts_reads_govc_esxcli_json(monkeypatch):
    replies = {
        ("about", "-json"): {"About": {"Name": "VMware ESXi", "Version": "8.0.3", "Build": "24859861"}},
        ("system", "hostname", "get"): {"Values": [{"FullyQualifiedDomainName": ["ESXi01.lab.example"]}]},
        ("network", "ip", "interface", "ipv4", "get"): {"Values": [{"Name": ["vmk0"], "IPv4Address": ["192.0.2.20"], "IPv4Netmask": ["255.255.255.0"], "AddressType": ["STATIC"]}]},
        ("network", "vswitch", "standard", "portgroup", "list"): {"Values": [{"Name": ["VM Network"], "VLANID": ["0"]}, {"Name": ["Management Network"], "VLANID": ["0"]}]},
        ("storage", "core", "device", "partition", "list"): {"Values": [
            {"Device": ["naa.600508b1001c0000"], "Partition": ["0"]},
            {"Device": ["naa.600508b1001c0000"], "Partition": ["1"]},
            {"Device": ["naa.600508b1001c0000"], "Partition": ["5"]}]},
        ("storage", "vmfs", "extent", "list"): {"Values": [{"VolumeName": ["datastore1"], "DeviceName": ["naa.600508b1001c0000"]}]},
    }

    def fake(ip, password, *args):
        key = args[2:] if args[:2] == ("host.esxcli", "-json") else args
        return replies[tuple(key)]

    monkeypatch.setattr(govc, "run", fake)
    facts = govc.host_facts("192.0.2.20", "x")
    assert facts["product"] == "VMware ESXi" and facts["fqdn"] == "esxi01.lab.example"
    assert facts["vmk0"] == {"ip": "192.0.2.20", "netmask": "255.255.255.0", "type": "STATIC"}
    assert facts["management_vlan"] == "0"
    assert facts["partitions"] == {"naa.600508b1001c0000": 2}
    assert facts["datastores"] == [{"name": "datastore1", "disk": "naa.600508b1001c0000"}]
    json.dumps(facts)


def test_datastore_create_names_the_host_it_runs_on(monkeypatch):
    calls = []

    def fake(ip, password, *args):
        calls.append(args)
        return "/ha-datacenter/host/esxi01.lab.example/esxi01.lab.example\n" if args[0] == "find" else None

    monkeypatch.setattr(govc, "run", fake)
    govc.create_vmfs_datastore("192.0.2.20", "x", "VMdata", "naa.600508b1001cdata")
    assert calls[-1] == ("datastore.create", "-type", "vmfs", "-name", "VMdata", "-disk", "naa.600508b1001cdata",
                         "/ha-datacenter/host/esxi01.lab.example/esxi01.lab.example")
