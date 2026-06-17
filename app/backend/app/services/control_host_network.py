from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from ipaddress import IPv4Interface, IPv4Network, ip_interface, ip_network
from typing import Any


RECHECK_COMMAND = "ip -4 -o addr show scope global"


def control_host_network_status(
    profile_context: dict[str, Any] | None = None,
    *,
    local_cidrs: list[str] | tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = (now or datetime.now(UTC)).isoformat()
    active_subnet_text = _active_subnet(profile_context or {})
    active_subnet = _parse_network(active_subnet_text)
    detected_cidrs = (
        list(local_cidrs)
        if local_cidrs is not None
        else [_test_fixture_cidr(active_subnet)]
        if _use_test_fixture_network() and active_subnet is not None
        else _local_ipv4_cidrs()
    )
    local_interfaces = _parse_interfaces(detected_cidrs)

    if active_subnet is None:
        return _payload(
            status="not_checked",
            classification="active_subnet_missing",
            active_subnet=active_subnet_text,
            local_cidrs=detected_cidrs,
            matching_cidrs=[],
            checked_at=checked_at,
            source_type="not_checked",
            message="Control host subnet visibility is not checked because the active lab subnet is not set.",
            warnings=["Set an active lab subnet before treating provider visibility as current."],
            next_action="Select or correct the active lab setup subnet, then recheck provider status.",
        )

    matching = [
        str(interface)
        for interface in local_interfaces
        if interface.ip.version == 4 and interface.ip in active_subnet
    ]
    if matching:
        return _payload(
            status="ready",
            classification="on_active_subnet",
            active_subnet=str(active_subnet),
            local_cidrs=detected_cidrs,
            matching_cidrs=matching,
            checked_at=checked_at,
            source_type=_source_type(local_cidrs),
            message=f"Control host has an IPv4 address on active lab subnet {active_subnet}.",
            warnings=[],
            next_action="Provider read-only checks may be refreshed from this host.",
        )

    blocker = (
        f"Control host has no IPv4 address on active lab subnet {active_subnet}; "
        "cached provider evidence cannot prove current visibility from this app host."
    )
    return _payload(
        status="blocked",
        classification="not_on_active_subnet",
        active_subnet=str(active_subnet),
        local_cidrs=detected_cidrs,
        matching_cidrs=[],
        checked_at=checked_at,
        source_type=_source_type(local_cidrs),
        message=blocker,
        blockers=[blocker],
        next_action=(
            f"Move this app host onto {active_subnet}, select the lab setup that matches the host network, "
            "or run validation from a control host on the active lab subnet."
        ),
    )


def _active_subnet(profile_context: dict[str, Any]) -> str | None:
    plan = profile_context.get("resolved_address_plan")
    if isinstance(plan, dict) and plan.get("subnet"):
        return str(plan.get("subnet"))
    profile = profile_context.get("active_profile")
    if isinstance(profile, dict):
        resolved = profile.get("resolved_address_plan")
        if isinstance(resolved, dict) and resolved.get("subnet"):
            return str(resolved.get("subnet"))
        if profile.get("subnet_cidr"):
            return str(profile.get("subnet_cidr"))
    return None


def _local_ipv4_cidrs() -> list[str]:
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    cidrs: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet":
            cidrs.append(parts[3])
    return _unique(cidrs)


def _parse_network(value: str | None) -> IPv4Network | None:
    if not value:
        return None
    try:
        network = ip_network(value, strict=False)
    except ValueError:
        return None
    return network if isinstance(network, IPv4Network) else None


def _parse_interfaces(values: list[str] | tuple[str, ...]) -> list[IPv4Interface]:
    interfaces: list[IPv4Interface] = []
    for value in values:
        try:
            interface = ip_interface(str(value))
        except ValueError:
            continue
        if isinstance(interface, IPv4Interface):
            interfaces.append(interface)
    return interfaces


def _source_type(local_cidrs: list[str] | tuple[str, ...] | None) -> str:
    if local_cidrs is not None:
        return "live_probe"
    if _use_test_fixture_network():
        return "test_fixture"
    return "live_probe"


def _test_fixture_cidr(active_subnet: IPv4Network) -> str:
    host_ip = active_subnet.network_address + 5
    if host_ip not in active_subnet:
        host_ip = active_subnet.network_address
    return f"{host_ip}/{active_subnet.prefixlen}"


def _use_test_fixture_network() -> bool:
    return os.getenv("INFRA_CONFIG_TEST_ISOLATE_REAL_LAB_ENV") == "1"


def _payload(
    *,
    status: str,
    classification: str,
    active_subnet: str | None,
    local_cidrs: list[str],
    matching_cidrs: list[str],
    checked_at: str,
    source_type: str,
    message: str,
    next_action: str,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "classification": classification,
        "active_subnet": active_subnet,
        "local_ipv4_cidrs": _unique(local_cidrs),
        "matching_local_ipv4_cidrs": _unique(matching_cidrs),
        "checked_at": checked_at,
        "source_type": source_type,
        "freshness": "current" if source_type in {"live_probe", "test_fixture"} else "not_checked",
        "message": message,
        "blockers": blockers or [],
        "warnings": warnings or [],
        "next_action": next_action,
        "recheck_command": RECHECK_COMMAND,
    }


def _unique(values: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
