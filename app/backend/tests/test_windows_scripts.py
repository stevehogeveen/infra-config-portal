from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_SCRIPTS = REPO_ROOT / "app" / "scripts"
APP_MAKEFILE = REPO_ROOT / "app" / "Makefile"
ROOT_MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_windows_powershell_helpers_parse() -> None:
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not available on this platform")

    scripts = sorted(APP_SCRIPTS.glob("*.ps1"))
    assert scripts

    for script in scripts:
        command = (
            "$errors = $null; "
            f"$content = Get-Content -LiteralPath '{script}' -Raw; "
            "[System.Management.Automation.PSParser]::Tokenize($content, [ref]$errors) > $null; "
            "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f"{script.name} failed to parse: {result.stderr}"


def test_backend_venv_script_self_heals_broken_venv() -> None:
    script = (APP_SCRIPTS / "ensure-backend-venv.ps1").read_text(encoding="utf-8")

    assert "function Test-Python" in script
    assert "Refusing to remove backend venv outside backend root" in script
    assert "Remove-Item -LiteralPath $resolvedVenv.Path -Recurse -Force" in script


def test_backend_venv_prefers_workflow_python_before_launcher_fallback() -> None:
    script = (APP_SCRIPTS / "ensure-backend-venv.ps1").read_text(encoding="utf-8")

    path_python = script.index("Get-Command python")
    path_venv = script.index("& python -m venv")
    launcher_python = script.index("$pythonLauncher = Get-Command py")
    launcher_venv = script.index("& py -3 -m venv")

    assert path_python < path_venv < launcher_python < launcher_venv


def test_windows_doctor_accepts_backend_venv_python() -> None:
    script = (APP_SCRIPTS / "windows-doctor.ps1").read_text(encoding="utf-8")

    assert "backend venv:" in script
    assert "Python 3 is not on PATH and backend venv is not ready" in script


def test_start_scripts_preflight_port_conflicts() -> None:
    backend = (APP_SCRIPTS / "start-backend.ps1").read_text(encoding="utf-8")
    frontend = (APP_SCRIPTS / "start-frontend.ps1").read_text(encoding="utf-8")

    for script, label in ((backend, "Backend"), (frontend, "Frontend")):
        assert "function Test-PortAvailable" in script
        assert "[System.Net.Sockets.TcpListener]::new" in script
        assert f"{label} port $HostName`:$Port is already in use" in script
        assert "rerun with -Port <free-port>" in script


def test_backend_start_uses_explicit_env_saved_mode_precedence() -> None:
    script = (APP_SCRIPTS / "start-backend.ps1").read_text(encoding="utf-8")

    requested_index = script.index("if ($RequestedMode")
    environment_index = script.index("if ($env:PROVIDER_MODE")
    saved_index = script.index('$modePath = Join-Path $RepositoryRoot ".local\\app-mode.env"')
    fallback_index = script.index('return "mock"')

    assert requested_index < environment_index < saved_index < fallback_index
    assert '$env:PROVIDER_MODE = Resolve-ProviderMode' in script
    assert 'ValidateSet("", "mock", "local-readonly", "local-lab-readwrite")' in script


def test_one_command_windows_launcher_is_owned_and_fail_closed() -> None:
    launcher = (APP_SCRIPTS / "start-lab-builder.ps1").read_text(encoding="utf-8")
    stopper = (APP_SCRIPTS / "stop-lab-builder.ps1").read_text(encoding="utf-8")

    assert "Wait-HttpReady" in launcher
    assert "/health" in launcher
    assert "/overview" in launcher
    assert "Start-Process" in launcher
    assert "-WindowStyle Hidden" in launcher
    assert "Stop-OwnedProcess -Process $frontendProcess" in launcher
    assert "Stop-OwnedProcess -Process $backendProcess" in launcher
    assert 'schema_version = "lab-builder-windows-runtime/v1"' in launcher
    assert "backend_started_at" in launcher
    assert "frontend_started_at" in launcher
    assert "taskkill.exe /PID $Process.Id /T /F" in launcher

    assert "Refusing to stop process" in stopper
    assert "start time does not match" in stopper
    assert "taskkill.exe /PID $processId /T /F" in stopper
    assert 'Remove-Item -LiteralPath $pidPath -Force' in stopper


def test_hardware_smoke_script_keeps_real_lab_lane_explicit() -> None:
    script = (APP_SCRIPTS / "hardware-smoke.ps1").read_text(encoding="utf-8")

    assert 'ValidateSet("local-readonly", "local-lab-readwrite")' in script
    assert 'Refusing hardware smoke in local-lab-readwrite without -AllowWriteMode' in script
    assert "[switch]$ValidatePlan" in script
    assert "hardware-smoke-plan.json" in script
    assert "schema_version = \"hardware-smoke-plan/v1\"" in script
    assert "function Test-HardwareSmokePlan" in script
    assert "provider_smoke_require_real must be true" in script
    assert "step command contains unsafe token" in script
    assert "$global:LASTEXITCODE = 0" in script
    assert "failed with exit code $LASTEXITCODE" in script
    assert 'Set-EnvValue "PROVIDER_SMOKE_REQUIRE_REAL" "true"' in script
    assert 'Set-EnvValue "LAB_CLOSED_LOOP_ACK" "YES"' in script
    assert 'Set-EnvValue "LAB_READONLY_ACK" "YES"' in script
    assert "scripts\\provider_smoke.py" in script
    assert "scripts\\operator_readonly_sweep.py" in script
    assert "Dry run complete. Re-run without -WhatIfOnly to execute." in script


def test_qa_failure_packet_script_is_advisory_wrapper() -> None:
    script = (APP_SCRIPTS / "qa-failure-packet.ps1").read_text(encoding="utf-8")

    assert "scripts\\qa_failure_packet.py" in script
    assert "--note $Note" in script
    assert "--max-artifacts $MaxArtifacts" in script
    assert "--validate-latest" in script
    assert "$ValidateLatest" in script
    assert "ensure-backend-venv.ps1" in script


def test_qa_artifact_health_script_validates_all_contracts() -> None:
    script = (APP_SCRIPTS / "qa-artifact-health.ps1").read_text(encoding="utf-8")

    assert "qa-artifact-health/v1" in script
    assert "qa-artifact-health.json" in script
    assert "fast-verify.ps1\") -ValidatePlan" in script
    assert "hardware-smoke.ps1\") -ValidatePlan" in script
    assert "qa-failure-packet.ps1\") -ValidateLatest" in script
    assert "openapi_contract_probe.py" in script
    assert "openapi-contract-probe.json" in script
    assert "qa_capability_audit.py" in script
    assert "qa-capability-audit.json" in script
    assert "It does not run tests, workflow actions, provider probes, hardware commands, or external AI calls." in script
    assert "GenerateMissingPlans" in script


def test_fast_verify_writes_plan_and_packets_failures() -> None:
    script = (APP_SCRIPTS / "fast-verify.ps1").read_text(encoding="utf-8")

    assert "[switch]$NoFailurePacket" in script
    assert "[switch]$ValidatePlan" in script
    assert "fast-verify-plan.json" in script
    assert "advisory_failure_packet_enabled" in script
    assert "step_details" in script
    assert "$stepCommands" in script
    assert "$script:stepReasons" in script
    assert "function Test-FastVerifyPlan" in script
    assert "step_details count must match planned_steps count" in script
    assert "step detail command contains unsafe token" in script
    assert "function New-FailurePacket" in script
    assert "$global:LASTEXITCODE = 0" in script
    assert "failed with exit code $LASTEXITCODE" in script
    assert "scripts\\qa_failure_packet.py" in script
    assert "tests\\test_qa_failure_packet.py" in script
    assert '"backend-openapi-contract"' in script
    assert "scripts\\openapi_contract_probe.py" in script
    assert "tests\\test_openapi_contract_probe.py" in script
    assert '"backend-qa-capability-audit"' in script
    assert "scripts\\qa_capability_audit.py" in script
    assert "tests\\test_qa_capability_audit.py" in script
    assert '"frontend-component-tests"' in script
    assert "npm run test:component" in script
    assert '"backend-windows-scripts"' in script
    assert "tests\\test_windows_scripts.py" in script
    assert "--note \"fast-verify step failed: $StepName\"" in script
    assert "Failure packets are redacted, advisory-only, and do not call external AI services." in script


def test_ci_runs_fast_verify_and_uploads_advisory_artifacts() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "Windows Fast Verify Gate" in workflow
    assert ".\\scripts\\fast-verify.ps1 -Full" in workflow
    assert "artifacts/codex-runs/fast-verify-plan.json" in workflow
    assert "artifacts/codex-runs/qa-failure-packets" in workflow
    assert "artifacts/codex-runs/openapi-contract-probe.json" in workflow
    assert "artifacts/codex-runs/qa-capability-audit.json" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "if-no-files-found: ignore" in workflow


def test_app_makefile_uses_cross_platform_backend_venv_python() -> None:
    makefile = APP_MAKEFILE.read_text(encoding="utf-8")

    assert ".venv/Scripts/python.exe" in makefile
    assert "$(VENV_PY) -m pip install --upgrade pip" in makefile
    assert "$(BACKEND_VENV_PY) -m uvicorn" in makefile
    assert "PROVIDER_MODE=mock $(BACKEND_VENV_PY) -m pytest -q" in makefile
    assert ".venv/bin/pytest" not in makefile
    assert ".venv/bin/uvicorn" not in makefile


def test_root_makefile_runs_frontend_component_tests_before_build() -> None:
    makefile = ROOT_MAKEFILE.read_text(encoding="utf-8")

    assert "npm run test:component" in makefile
    assert makefile.index("npm run test:component") < makefile.index("npm run build")


def test_windows_check_runs_frontend_component_tests_before_build() -> None:
    script = (APP_SCRIPTS / "check-windows.ps1").read_text(encoding="utf-8")

    assert 'Invoke-Step "Frontend component tests"' in script
    assert "npm run test:component" in script
    assert script.index("npm run test:component") < script.index("npm run build")


def test_esxi_wrapper_scripts_use_shared_env_loader_before_service_imports() -> None:
    scripts = {
        "esxi_netapp_datastore_workflow.py": "from app.services.esxi_netapp_datastore import",
        "esxi_management_recovery.py": "from app.services.esxi_management_recovery import",
    }
    for name, workflow_import in scripts.items():
        script = (REPO_ROOT / "app" / "backend" / "scripts" / name).read_text(encoding="utf-8")
        loader_index = script.index("load_env_file(REAL_LAB_ENV)")
        service_import_index = script.index(workflow_import)

        assert loader_index < service_import_index
        assert "split(\"=\", 1)" not in script
        assert "read_text(encoding=\"utf-8\").splitlines()" not in script
