from __future__ import annotations

from app.services import cisco_current_intent


def test_cisco_current_intent_diff_parses_vlan_and_interface_drift(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cisco_current_intent, "CODEX_RUN_DIR", tmp_path)
    monkeypatch.setattr(cisco_current_intent, "CISCO_INTENT_DIFF_JSON", tmp_path / "diff.json")
    monkeypatch.setattr(cisco_current_intent, "CISCO_INTENT_DIFF_REPORT", tmp_path / "diff.md")
    monkeypatch.setattr(
        cisco_current_intent,
        "active_cisco_network_defaults",
        lambda: {"management_vlan": "10", "planned_gateway": "192.168.1.1"},
    )

    class FakeCiscoAnsibleAdapter:
        def probe(self) -> dict[str, object]:
            return {
                "status": "ok",
                "version_hint": "17.15.05",
                "command_results": {
                    "show version": {"captured": True, "version_hint": "17.15.05", "stdout_summary": []},
                    "show vlan brief": {
                        "captured": True,
                        "stdout_summary": [
                            "1    default                          active",
                            "10   LAB-MGMT-10                      active",
                            "20   ESXI-HOSTS                       active",
                        ],
                    },
                    "show interfaces status": {
                        "captured": True,
                        "stdout_summary": [
                            "Gi1/0/1 operator connected 10 a-full a-1000 10/100/1000BaseTX",
                            "Gi1/0/3 esxi-a connected trunk a-full a-1000 10/100/1000BaseTX",
                            "Gi1/0/5 netapp-a connected 10 a-full a-1000 10/100/1000BaseTX",
                        ],
                    },
                    "show running-config | include spanning-tree portfast": {
                        "captured": True,
                        "stdout_summary": ["spanning-tree portfast default"],
                    },
                    "show running-config | include spanning-tree bpduguard": {
                        "captured": True,
                        "stdout_summary": ["spanning-tree portfast bpduguard default"],
                    },
                    "show running-config | include ip access-list|ip access-group": {
                        "captured": True,
                        "stdout_summary": [
                            "ip access-list extended MGMT-IN",
                            "ip access-list extended STORAGE-NFS-IN",
                            "ip access-list extended DROP-ALL",
                        ],
                    },
                },
                "warnings": [],
                "blockers": [],
            }

    monkeypatch.setattr(cisco_current_intent, "CiscoAnsibleAdapter", FakeCiscoAnsibleAdapter)

    result = cisco_current_intent.get_cisco_current_intent_diff(write_report=True)

    assert result["status"] == "warning"
    assert result["source_type"] == "live_probe"
    assert result["diff"]["vlan"]["missing"] == ["30", "999"]
    assert any(item["port"] == "Gi1/0/5" for item in result["diff"]["ports"])
    assert result["diff"]["guardrails"]["bpdu_guard"]["status"] == "ready"
    assert result["diff"]["guardrails"]["acl_lanes"]["status"] == "ready"
    assert result["diff"]["guardrails"]["blackhole_vlan"]["status"] == "warning"
    assert result["diff"]["not_checked"] == []
    preview = result["candidate_config_preview"]
    assert preview["status"] == "ready"
    assert "vlan 30" in preview["commands"]
    assert "vlan 999" in preview["commands"]
    assert "interface Gi1/0/5" in preview["commands"]
    assert not any("write memory" in command for command in preview["commands"])
    assert not any("no vlan" in command for command in preview["commands"])
    remediation = result["remediation_plan"]
    assert remediation["status"] == "warning"
    assert remediation["safe_to_render_commands"] is True
    assert remediation["command_count"] == len(preview["commands"])
    remediation_steps = {step["label"]: step for step in remediation["steps"]}
    assert remediation_steps["Create missing VLANs"]["detail"] == "30, 999"
    assert remediation_steps["Align intended ports"]["status"] == "warning"
    assert "blackhole_vlan: 999" in remediation_steps["Review guardrails"]["detail"]
    assert "1" in remediation_steps["Preserve unexpected VLANs"]["detail"]
    assert (tmp_path / "diff.json").exists()
    report = (tmp_path / "diff.md").read_text(encoding="utf-8").strip()
    assert "Candidate Config Preview" in report
    assert "Remediation Plan" in report
    assert "interface Gi1/0/5" in report


def test_cisco_current_intent_diff_keeps_guardrails_not_checked_without_narrow_output(monkeypatch) -> None:
    monkeypatch.setattr(
        cisco_current_intent,
        "active_cisco_network_defaults",
        lambda: {"management_vlan": "10", "planned_gateway": "192.168.1.1"},
    )

    class FakeCiscoAnsibleAdapter:
        def probe(self) -> dict[str, object]:
            return {
                "status": "ok",
                "command_results": {
                    "show version": {"captured": True, "version_hint": "17.15.05", "stdout_summary": []},
                    "show vlan brief": {
                        "captured": True,
                        "stdout_summary": ["10   LAB-MGMT-10                      active"],
                    },
                    "show interfaces status": {
                        "captured": True,
                        "stdout_summary": ["Gi1/0/1 operator connected 10 a-full a-1000 10/100/1000BaseTX"],
                    },
                },
                "warnings": [],
                "blockers": [],
            }

    monkeypatch.setattr(cisco_current_intent, "CiscoAnsibleAdapter", FakeCiscoAnsibleAdapter)

    result = cisco_current_intent.get_cisco_current_intent_diff(write_report=False)

    assert result["status"] == "warning"
    assert result["diff"]["guardrails"]["bpdu_guard"]["status"] == "not_checked"
    assert result["diff"]["guardrails"]["acl_lanes"]["status"] == "not_checked"
    assert {item["area"] for item in result["diff"]["not_checked"]} == {"bpdu_guard", "acl_lanes"}


def test_cisco_current_intent_diff_does_not_count_command_echo_as_guardrail_proof(monkeypatch) -> None:
    monkeypatch.setattr(
        cisco_current_intent,
        "active_cisco_network_defaults",
        lambda: {"management_vlan": "10", "planned_gateway": "192.168.1.1"},
    )

    class FakeCiscoAnsibleAdapter:
        def probe(self) -> dict[str, object]:
            return {
                "status": "ok",
                "command_results": {
                    "show version": {"captured": True, "version_hint": "17.15.05", "stdout_summary": []},
                    "show vlan brief": {
                        "captured": True,
                        "stdout_summary": ["10   LAB-MGMT-10                      active"],
                    },
                    "show interfaces status": {
                        "captured": True,
                        "stdout_summary": ["Gi1/0/1 operator connected 10 a-full a-1000 10/100/1000BaseTX"],
                    },
                    "show running-config | include spanning-tree portfast": {
                        "captured": True,
                        "stdout_summary": [
                            "show running-config | include spanning-tree portfast",
                            "lab-cisco-switch#",
                        ],
                    },
                    "show running-config | include spanning-tree bpduguard": {
                        "captured": True,
                        "stdout_summary": [
                            "show running-config | include spanning-tree bpduguard",
                            "lab-cisco-switch#",
                        ],
                    },
                    "show running-config | include ip access-list|ip access-group": {
                        "captured": True,
                        "stdout_summary": [
                            "show running-config | include ip access-list|ip access-group",
                            "lab-cisco-switch#",
                        ],
                    },
                },
                "warnings": [],
                "blockers": [],
            }

    monkeypatch.setattr(cisco_current_intent, "CiscoAnsibleAdapter", FakeCiscoAnsibleAdapter)

    result = cisco_current_intent.get_cisco_current_intent_diff(write_report=False)

    assert result["diff"]["guardrails"]["bpdu_guard"]["status"] == "warning"
    assert result["diff"]["guardrails"]["bpdu_guard"]["matched"] == []
    assert result["diff"]["guardrails"]["acl_lanes"]["status"] == "warning"
    assert result["diff"]["guardrails"]["acl_lanes"]["matched"] == []


def test_cisco_current_intent_diff_blocks_without_required_show_output(monkeypatch) -> None:
    class FakeCiscoAnsibleAdapter:
        def probe(self) -> dict[str, object]:
            return {"status": "ok", "command_results": {}, "warnings": [], "blockers": []}

    monkeypatch.setattr(cisco_current_intent, "CiscoAnsibleAdapter", FakeCiscoAnsibleAdapter)

    result = cisco_current_intent.get_cisco_current_intent_diff(write_report=False)

    assert result["status"] == "blocked"
    assert "show vlan brief" in " ".join(result["blockers"])
    assert result["candidate_config_preview"]["status"] == "blocked"
    assert result["candidate_config_preview"]["commands"] == []
    assert result["remediation_plan"]["status"] == "blocked"
    assert result["remediation_plan"]["safe_to_render_commands"] is False
