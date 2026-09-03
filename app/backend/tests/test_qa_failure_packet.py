from __future__ import annotations

import json
from pathlib import Path

from scripts import qa_failure_packet


def test_qa_failure_packet_collects_and_redacts_test_artifacts(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    test_result = app_root / "frontend" / "test-results" / "failed-flow" / "error-context.md"
    test_result.parent.mkdir(parents=True)
    test_result.write_text(
        "locator failed\npassword=super-secret-password\nnext check should inspect the route",
        encoding="utf-8",
    )
    lastfailed = app_root / "backend" / ".pytest_cache" / "v" / "cache" / "lastfailed"
    lastfailed.parent.mkdir(parents=True)
    lastfailed.write_text(json.dumps({"tests/test_example.py::test_failure": True}), encoding="utf-8")

    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)
    monkeypatch.setattr(qa_failure_packet, "OUTPUT_DIR", repo_root / "artifacts" / "codex-runs" / "qa-failure-packets")
    monkeypatch.setenv("LAB_PASSWORD", "super-secret-password")

    packet = qa_failure_packet.create_qa_failure_packet(note="button broke", output_dir=qa_failure_packet.OUTPUT_DIR)

    assert packet["schema_version"] == "qa-failure-packet/v1"
    assert packet["advisory_only"] is True
    assert packet["advisory_source"] == "local_redacted_evidence_packet"
    assert packet["not_attempted"] == [
        "test execution",
        "workflow action execution",
        "provider probe execution",
        "hardware access",
        "external AI/API call",
    ]
    serialized = json.dumps(packet)
    assert "super-secret-password" not in serialized
    assert "password=REDACTED" in serialized
    assert "tests/test_example.py::test_failure" in serialized
    assert "Stay advisory only" in packet["suggested_ai_prompt"]
    assert "Do not suggest write" in packet["suggested_ai_prompt"]
    assert packet["advisory_triage"]["schema_version"] == "advisory-triage/v1"
    assert packet["advisory_triage"]["probable_area"] == "backend-pytest"
    assert packet["advisory_triage"]["confidence"] == "medium"
    assert packet["advisory_triage"]["evidence_kinds"] == ["playwright", "pytest-cache"]
    assert "pytest <failing test path> -q" in packet["advisory_triage"]["safe_verification_command"]
    assert "write workflow actions" in packet["advisory_triage"]["unsafe_actions_excluded"]
    assert "destructive workflow actions" in packet["advisory_triage"]["unsafe_actions_excluded"]
    assert (qa_failure_packet.OUTPUT_DIR / "latest.json").is_file()
    assert (qa_failure_packet.OUTPUT_DIR / "latest.md").is_file()
    markdown = (qa_failure_packet.OUTPUT_DIR / "latest.md").read_text(encoding="utf-8")
    assert "## Advisory Triage" in markdown
    assert "Safe verification" in markdown
    validation = qa_failure_packet.validate_qa_failure_packet_path(qa_failure_packet.OUTPUT_DIR / "latest.json")
    assert validation["valid"] is True
    assert validation["errors"] == []


def test_qa_failure_packet_reports_empty_evidence(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    app_root.mkdir()
    output_dir = repo_root / "packets"
    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)

    packet = qa_failure_packet.create_qa_failure_packet(output_dir=output_dir)

    assert packet["evidence"] == []
    assert "No recent pytest" in packet["summary"]
    assert packet["advisory_triage"]["probable_area"] == "unknown"
    assert packet["advisory_triage"]["confidence"] == "low"
    assert packet["advisory_triage"]["safe_verification_command"] == ".\\scripts\\fast-verify.ps1 -WhatIfOnly"
    assert (output_dir / "latest.json").is_file()


def test_qa_failure_packet_triages_hardware_without_write_suggestion(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    smoke = app_root / "artifacts" / "real-lab" / "provider-smoke.json"
    smoke.parent.mkdir(parents=True)
    smoke.write_text(
        json.dumps({"status": "failed", "summary": "provider timeout connection refused"}),
        encoding="utf-8",
    )
    output_dir = repo_root / "packets"
    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)

    packet = qa_failure_packet.create_qa_failure_packet(note="real-lab unreachable", output_dir=output_dir)

    triage = packet["advisory_triage"]
    assert triage["probable_area"] == "hardware-smoke"
    assert triage["safe_verification_command"] == ".\\scripts\\hardware-smoke.ps1 -WhatIfOnly"
    assert "write" not in triage["safe_verification_command"].lower()
    assert "destructive" not in triage["safe_verification_command"].lower()
    assert "external AI/API calls" in triage["unsafe_actions_excluded"]


def test_qa_failure_packet_does_not_treat_provider_test_names_as_hardware(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    lastfailed = app_root / "backend" / ".pytest_cache" / "v" / "cache" / "lastfailed"
    lastfailed.parent.mkdir(parents=True)
    lastfailed.write_text(json.dumps({"tests/test_provider_registry.py::test_provider_mapping": True}), encoding="utf-8")
    output_dir = repo_root / "packets"
    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)

    packet = qa_failure_packet.create_qa_failure_packet(note="provider unit test failed", output_dir=output_dir)

    triage = packet["advisory_triage"]
    assert triage["probable_area"] == "backend-pytest"
    assert triage["safe_verification_command"].startswith("cd backend")


def test_qa_failure_packet_keeps_mixed_test_timeout_in_test_lane(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    lastfailed = app_root / "backend" / ".pytest_cache" / "v" / "cache" / "lastfailed"
    lastfailed.parent.mkdir(parents=True)
    lastfailed.write_text(json.dumps({"tests/test_api.py::test_timeout_case": True}), encoding="utf-8")
    last_run = app_root / "frontend" / "test-results" / ".last-run.json"
    last_run.parent.mkdir(parents=True)
    last_run.write_text(json.dumps({"status": "failed", "message": "test timeout exceeded"}), encoding="utf-8")
    output_dir = repo_root / "packets"
    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)

    packet = qa_failure_packet.create_qa_failure_packet(note="timeout while testing", output_dir=output_dir)

    triage = packet["advisory_triage"]
    assert triage["probable_area"] == "backend-pytest"
    assert triage["safe_verification_command"].startswith("cd backend")


def test_qa_failure_packet_validation_rejects_unsafe_triage_command(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    app_root.mkdir()
    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)
    packet = qa_failure_packet.create_qa_failure_packet(output_dir=repo_root / "packets")
    packet["advisory_triage"]["safe_verification_command"] = ".\\scripts\\hardware-smoke.ps1 -AllowWriteMode"

    validation = qa_failure_packet.validate_qa_failure_packet(packet)

    assert validation["valid"] is False
    assert any("unsafe token" in error for error in validation["errors"])


def test_qa_failure_packet_validation_rejects_missing_schema(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    app_root = repo_root / "app"
    app_root.mkdir()
    monkeypatch.setattr(qa_failure_packet, "REPO_ROOT", repo_root)
    monkeypatch.setattr(qa_failure_packet, "APP_ROOT", app_root)
    packet = qa_failure_packet.create_qa_failure_packet(output_dir=repo_root / "packets")
    packet.pop("schema_version")

    validation = qa_failure_packet.validate_qa_failure_packet(packet)

    assert validation["valid"] is False
    assert "schema_version must be qa-failure-packet/v1" in validation["errors"]
