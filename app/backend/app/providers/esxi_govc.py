"""Sign in to a freshly installed ESXi host with govc: read-only facts for verification, and the
single datastore-create command. The root password goes to govc through its environment only;
it never appears on a command line, in a log or in a returned value."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

TIMEOUT_SECONDS = 120


class GovcError(RuntimeError):
    """govc could not run or the host refused it. The message is safe to show."""


def available() -> bool:
    return shutil.which("govc") is not None


def _env(ip: str, password: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GOVC_")}
    env.update({
        "GOVC_URL": f"https://{ip}/sdk",
        "GOVC_USERNAME": "root",
        "GOVC_PASSWORD": password,
        # A fresh ESXi host presents its own self-signed certificate.
        "GOVC_INSECURE": "1",
    })
    return env


def run(ip: str, password: str, *args: str) -> Any:
    binary = shutil.which("govc")
    if not binary:
        raise GovcError("govc is not installed in the app's container.")
    try:
        result = subprocess.run([binary, *args], env=_env(ip, password), capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        raise GovcError("ESXi did not answer in time.") from None
    if result.returncode != 0:
        text = (result.stderr or result.stdout or "").strip().splitlines()
        reason = text[-1] if text else "govc failed."
        if "incorrect user name or password" in reason.lower() or "cannot complete login" in reason.lower():
            raise GovcError("ESXi refused the root sign-in (wrong password, or this is a different host).")
        raise GovcError(_scrub(reason, password)[:300])
    output = result.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def _scrub(text: str, password: str) -> str:
    from urllib.parse import quote, quote_plus

    for form in {password, quote(password, safe=""), quote_plus(password)}:
        if form:
            text = text.replace(form, "***")
    return text


def _lower(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key).lower(): _lower(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_lower(item) for item in value]
    return value


def _rows(payload: Any) -> list[dict[str, str]]:
    """govc host.esxcli -json: {"Values": [{"Field": ["value"], ...}]} -> [{"field": "value"}]."""
    data = _lower(payload) if payload is not None else {}
    values = data.get("values") if isinstance(data, dict) else None
    rows = []
    for row in values or []:
        if isinstance(row, dict):
            rows.append({key: (item[0] if isinstance(item, list) and item else item if not isinstance(item, list) else "") for key, item in row.items()})
    return rows


def esxcli(ip: str, password: str, *args: str) -> list[dict[str, str]]:
    return _rows(run(ip, password, "host.esxcli", "-json", *args))


def host_facts(ip: str, password: str) -> dict[str, Any]:
    """Read-only facts used to prove the install: product, name, address, VLAN, disks."""
    about = _lower(run(ip, password, "about", "-json")) or {}
    about = about.get("about", about) if isinstance(about, dict) else {}
    hostname = next(iter(esxcli(ip, password, "system", "hostname", "get")), {})
    interfaces = esxcli(ip, password, "network", "ip", "interface", "ipv4", "get")
    vmk0 = next((row for row in interfaces if row.get("name") == "vmk0"), {})
    portgroups = esxcli(ip, password, "network", "vswitch", "standard", "portgroup", "list")
    management = next((row for row in portgroups if row.get("name") == "Management Network"), {})
    partitions: dict[str, int] = {}
    for row in esxcli(ip, password, "storage", "core", "device", "partition", "list"):
        device = row.get("device", "")
        if device and str(row.get("partition", "0")) != "0":
            partitions[device] = partitions.get(device, 0) + 1
    extents = [{"name": row.get("volumename", ""), "disk": row.get("devicename", "")} for row in esxcli(ip, password, "storage", "vmfs", "extent", "list")]
    return {
        "product": about.get("name") or about.get("fullname") or "",
        "version": about.get("version") or "",
        "build": about.get("build") or "",
        "fqdn": (hostname.get("fullyqualifieddomainname") or "").lower(),
        "vmk0": {"ip": vmk0.get("ipv4address"), "netmask": vmk0.get("ipv4netmask"), "type": (vmk0.get("addresstype") or "").upper()},
        "management_vlan": management.get("vlanid"),
        "partitions": partitions,
        "datastores": extents,
    }


def host_path(ip: str, password: str) -> str:
    """The host's inventory path (standalone ESXi: /ha-datacenter/host/<name>/<name>)."""
    found = run(ip, password, "find", "/", "-type", "h")
    paths = [line.strip() for line in str(found or "").splitlines() if line.strip()]
    if len(paths) != 1:
        raise GovcError(f"Expected one ESXi host behind this address, found {len(paths)}.")
    return paths[0]


def create_vmfs_datastore(ip: str, password: str, name: str, disk: str) -> None:
    # datastore.create needs the host as its argument; without it govc refuses before sending.
    run(ip, password, "datastore.create", "-type", "vmfs", "-name", name, "-disk", disk, host_path(ip, password))


# ---------------------------------------------------------------- virtual machines

IMPORT_TIMEOUT_SECONDS = 4 * 60 * 60


def datastores(ip: str, password: str) -> list[dict[str, Any]]:
    data = _lower(run(ip, password, "datastore.info", "-json")) or {}
    rows = data.get("datastores") or data.get("datastore") or []
    result = []
    for row in rows if isinstance(rows, list) else []:
        summary = row.get("summary") or {}
        result.append({
            "name": summary.get("name") or row.get("name"),
            "capacity": int(summary.get("capacity") or 0),
            "free": int(summary.get("freespace") or 0),
        })
    return [r for r in result if r["name"]]


def networks(ip: str, password: str) -> list[str]:
    listing = run(ip, password, "ls", "/ha-datacenter/network")
    return [line.rsplit("/", 1)[-1] for line in str(listing or "").splitlines() if line.strip()]


def vm_info(ip: str, password: str, name: str) -> dict[str, Any] | None:
    """Power, VMware Tools and guest address of one VM, or None when it does not exist."""
    data = _lower(run(ip, password, "vm.info", "-json", name)) or {}
    machines = data.get("virtualmachines") or []
    if not machines:
        return None
    vm = machines[0]
    guest = vm.get("guest") or {}
    runtime = vm.get("runtime") or {}
    addresses = [
        address.get("ipaddress")
        for nic in guest.get("net") or []
        for address in ((nic.get("ipconfig") or {}).get("ipaddress") or [])
        if isinstance(address, dict)
    ]
    return {
        "power": runtime.get("powerstate"),
        "tools": guest.get("toolsrunningstatus"),
        "ip": guest.get("ipaddress"),
        "addresses": [a for a in addresses if a],
        "hostname": guest.get("hostname"),
        "guest_os": (vm.get("config") or {}).get("guestfullname") or guest.get("guestfullname"),
    }


def ovf_networks(ip: str, password: str, path: str) -> list[str]:
    """The network names the OVF/OVA declares (read locally by govc)."""
    spec = _lower(run(ip, password, "import.spec", path)) or {}
    return [m.get("name") for m in spec.get("networkmapping") or [] if m.get("name")]


def import_vm(ip: str, password: str, *, path: str, datastore: str, name: str, network: str, mappings: list[str],
              heartbeat=None) -> None:
    """Import an OVA/OVF as a powered-off, thin-provisioned VM. Long-running; call from a worker.
    heartbeat() is called about every 30 seconds while govc is still working."""
    import tempfile
    import time

    options = {
        "DiskProvisioning": "thin",
        "IPAllocationPolicy": "dhcpPolicy",
        "IPProtocol": "IPv4",
        "NetworkMapping": [{"Name": source, "Network": network} for source in mappings],
        "MarkAsTemplate": False,
        "PowerOn": False,
        "InjectOvfEnv": False,
        "WaitForIP": False,
        "Name": name,
    }
    binary = shutil.which("govc")
    if not binary:
        raise GovcError("govc is not installed in the app's container.")
    command = "import.ova" if path.lower().endswith(".ova") else "import.ovf"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(options, handle)
        options_path = handle.name
    deadline = time.monotonic() + IMPORT_TIMEOUT_SECONDS
    try:
        with tempfile.TemporaryFile("w+") as output:
            process = subprocess.Popen(
                [binary, command, "-options", options_path, "-ds", datastore, "-name", name, path],
                env=_env(ip, password), stdout=output, stderr=subprocess.STDOUT, text=True,
            )
            while process.poll() is None:
                if time.monotonic() > deadline:
                    process.kill()
                    raise GovcError("The import did not finish within four hours.")
                if heartbeat:
                    heartbeat()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
            output.seek(0)
            text = output.read().strip().splitlines()
    finally:
        os.unlink(options_path)
    if process.returncode != 0:
        raise GovcError(_scrub(text[-1] if text else "The import failed.", password)[:300])


def power_on(ip: str, password: str, name: str) -> None:
    run(ip, password, "vm.power", "-on", name)
