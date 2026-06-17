from __future__ import annotations

from datetime import UTC, datetime

from app.services.control_host_network import control_host_network_status


NOW = datetime(2026, 6, 16, 15, 0, tzinfo=UTC)


def test_control_host_network_ready_when_host_ip_is_on_active_subnet() -> None:
    result = control_host_network_status(
        {"resolved_address_plan": {"subnet": "10.10.8.0/24"}},
        local_cidrs=["10.10.8.25/24", "172.16.1.244/24"],
        now=NOW,
    )

    assert result["status"] == "ready"
    assert result["classification"] == "on_active_subnet"
    assert result["matching_local_ipv4_cidrs"] == ["10.10.8.25/24"]
    assert result["blockers"] == []


def test_control_host_network_blocks_when_host_ip_is_not_on_active_subnet() -> None:
    result = control_host_network_status(
        {"resolved_address_plan": {"subnet": "10.10.8.0/24"}},
        local_cidrs=["172.16.1.244/24", "192.168.1.240/24"],
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["classification"] == "not_on_active_subnet"
    assert result["matching_local_ipv4_cidrs"] == []
    assert "no IPv4 address on active lab subnet 10.10.8.0/24" in result["blockers"][0]
    assert result["recheck_command"] == "ip -4 -o addr show scope global"


def test_control_host_network_not_checked_without_active_subnet() -> None:
    result = control_host_network_status({}, local_cidrs=["10.10.8.25/24"], now=NOW)

    assert result["status"] == "not_checked"
    assert result["classification"] == "active_subnet_missing"
    assert result["warnings"] == [
        "Set an active lab subnet before treating provider visibility as current."
    ]
