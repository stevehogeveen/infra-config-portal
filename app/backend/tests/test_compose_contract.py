from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "app"


def test_backend_image_preserves_repository_layout_and_excludes_local_state() -> None:
    dockerfile = (APP_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "COPY . /workspace" in dockerfile
    assert "WORKDIR /workspace/app/backend" in dockerfile
    assert "WORKDIR /app" not in dockerfile
    assert ".env.*" in dockerignore
    assert ".local" in dockerignore
    assert "artifacts" in dockerignore
    assert "**/node_modules" in dockerignore


def test_compose_config_preserves_state_and_uses_same_origin_api_proxy() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose is not installed on this host")

    result = subprocess.run(
        [docker, "compose", "config", "--format", "json"],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    config = json.loads(result.stdout)
    services = config["services"]
    backend = services["backend"]
    frontend = services["frontend"]

    assert backend["build"]["context"] == str(REPO_ROOT)
    assert backend["environment"]["PROVIDER_MODE"] == "mock"
    assert any(mount["target"] == "/workspace/.local" for mount in backend["volumes"])
    assert any(mount["target"] == "/workspace/artifacts" for mount in backend["volumes"])
    assert frontend["environment"]["VITE_API_BASE_URL"] == ""
    assert frontend["environment"]["APP_PROXY_TARGET"] == "http://backend:8000"
    assert any(
        mount["target"] == "/workspace/app/frontend/node_modules"
        and mount["type"] == "volume"
        for mount in frontend["volumes"]
    )
